"""
VisionGuard AI - Clip Recorder

Records post-event video clips, finds matching snapshots, uploads both
to Cloudinary, and writes the resulting URLs to the event_evidence table.

Completely isolated from inference pipeline — runs as a separate process.
"""

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import threading
from collections import deque

import cv2
import subprocess
import redis

from .config import ClipConfig
from .uploader import CloudinaryUploader
from .database import Database

logger = logging.getLogger(__name__)


class ClipError:
    """Centralized intuitive error messages for clip recording."""
    OFFLINE = "Camera Stream Offline"
    NO_SIGNAL = "Capture Failed (No Signal)"
    BUFFER_EMPTY = "Memory Buffer Empty"
    TOO_OLD = "Event Too Old (Buffer Expired)"
    INTERNAL = "Recording Error (Hardware/IO)"
    TRANSCODE = "Transcoding Failed (FFmpeg)"


class ClipRecorder:
    """
    Orchestrates post-event clip recording and cloud upload.

    Flow for each event:
      1. Find existing snapshot from the detections directory
      2. Record a post-event clip from the camera source
      3. Upload snapshot to Cloudinary
      4. Upload clip to Cloudinary
      5. Write both URLs to event_evidence table
      6. Delete local clip file after successful upload
    """

    def __init__(self, config: ClipConfig) -> None:
        """
        Initialize clip recorder.

        Args:
            config: ClipConfig with all settings
        """
        self.config = config
        self.uploader = CloudinaryUploader(
            cloud_name=config.cloudinary_cloud_name,
            api_key=config.cloudinary_api_key,
            api_secret=config.cloudinary_api_secret,
        )
        self.db = Database(config)

        # Ensure local directories exist
        os.makedirs(config.clip_dir, exist_ok=True)
        os.makedirs(config.snapshot_dir, exist_ok=True)

        logger.info(
            "ClipRecorder initialized (PostgreSQL)",
            extra={
                "clip_dir": config.clip_dir,
                "snapshot_dir": config.snapshot_dir,
                "post_seconds": config.clip_post_seconds,
                "fps": config.camera_fps,
            },
        )

        # Multi-camera Rolling Buffer Strategy (Latency-Aware)
        # Dictionary of camera_source -> deque of (timestamp, cv2.Mat)
        self.frame_buffers: Dict[str, deque] = {}
        self.buffer_locks: Dict[str, threading.Lock] = {}
        
        # New: Auto-start buffers for Dashcam mode
        if self.config.enable_background_buffer:
            logger.info("CLIP_ENABLE_BACKGROUND_BUFFER=true. Dashcam mode active.")
        
        # We start the background capture threads here
        self._shutdown_event = threading.Event()
        self._capture_threads: Dict[str, threading.Thread] = {}
        
        # Optional: start persistent background buffer only when explicitly enabled
        if self.config.enable_background_buffer and self.config.camera_source:
            self._start_camera_buffer(self.config.camera_source)

    def _start_camera_buffer(self, camera_source: str):
        """Starts a background thread to maintain a rolling buffer for a camera source."""
        if camera_source in self._capture_threads:
            return
            
        # Store ~60 seconds of video dynamically to handle processing lag
        max_buffer_frames = self.config.camera_fps * 60 
        self.frame_buffers[camera_source] = deque(maxlen=max_buffer_frames)
        self.buffer_locks[camera_source] = threading.Lock()

        t = threading.Thread(
            target=self._camera_capture_loop,
            args=(camera_source,),
            daemon=True,
            name=f"Capture-{camera_source.split('/')[-1]}"
        )
        self._capture_threads[camera_source] = t
        t.start()
        
    def _camera_capture_loop(self, camera_source: str):
        """
        Continuously reads from RTSP into the ring buffer.
        Drains the OpenCV buffer as fast as possible to eliminate lag.
        """
        logger.info(f"Starting background ring buffer for {camera_source}")
        cap = None
        last_save_time = 0
        
        while not self._shutdown_event.is_set():
            try:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(camera_source)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        logger.warning(f"ClipRecorder buffer failed to connect to {camera_source}")
                        cap = None
                        time.sleep(2.0)
                        continue
                
                # Drain the buffer: grab frames as fast as possible
                ret = cap.grab()
                if not ret:
                    logger.warning(f"Failed to grab frame from {camera_source}, reconnecting...")
                    cap.release()
                    cap = None
                    continue
                
                # Only retrieve and store at the target FPS
                now = time.time()
                if now - last_save_time >= (1.0 / self.config.camera_fps):
                    ret, frame = cap.retrieve()
                    if ret and frame is not None:
                        with self.buffer_locks[camera_source]:
                            self.frame_buffers[camera_source].append((now, frame))
                        last_save_time = now
                
                # Minimal sleep to prevent 100% CPU, but keep buffer drained
                time.sleep(0.001)
                
            except Exception as e:
                logger.error(f"Error in ring buffer capture for {camera_source}: {e}")
                if cap:
                    cap.release()
                    cap = None
                time.sleep(2.0)
                
        if cap:
            cap.release()
            
    def shutdown(self):
        """Stops the background capture threads."""
        self._shutdown_event.set()
        for t in self._capture_threads.values():
            t.join(timeout=2.0)

    def start_dashcam_buffers(self, camera_sources: list):
        """
        Proactively start ring buffers for all known cameras.
        This ensures history is available BEFORE the first incident happens.
        """
        if not self.config.enable_background_buffer:
            return
            
        logger.info(f"Initializing dashcam buffers for {len(camera_sources)} cameras")
        for source in camera_sources:
            if source:
                self._start_camera_buffer(source)

    def _get_mask_faces_setting(self) -> bool:
        """Synchronously check face masking (Redis -> Postgres -> env defaults)."""
        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                socket_connect_timeout=2,
            )
            raw = r.get("vg:system_settings")
            r.close()
            if raw:
                import json
                data = json.loads(raw)
                if isinstance(data, dict):
                    return bool(data.get("privacy", {}).get("maskFaces", False))
        except Exception as e:
            logger.debug(f"Redis mask_faces lookup failed in clip recorder: {e}")

        try:
            import json
            import psycopg2
            db_url = self.db.url
            conn = psycopg2.connect(db_url, connect_timeout=2)
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM system_settings ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row and row[0]:
                stored = row[0]
                if isinstance(stored, str):
                    stored = json.loads(stored)
                return bool(stored.get("privacy", {}).get("maskFaces", False))
        except Exception as e:
            logger.debug(f"Postgres mask_faces lookup failed in clip recorder: {e}")

        # Final fallback: env default
        return os.getenv("PRIVACY_MASK_FACES", "false").strip().lower() in {"1", "true", "yes", "on"}

    async def get_system_settings(self) -> dict:
        """Fetch settings using Redis -> Postgres -> env defaults fallback."""
        defaults = {
            "privacy": {
                "maskFaces": os.getenv("PRIVACY_MASK_FACES", "false").strip().lower() in {"1", "true", "yes", "on"}
            },
            "clips": {
                "preSeconds": int(float(os.getenv("CLIP_PRE_SECONDS", "0"))),
                "postSeconds": int(float(os.getenv("CLIP_POST_SECONDS", "10"))),
                "enableBackgroundBuffer": os.getenv("CLIP_ENABLE_BACKGROUND_BUFFER", "false").strip().lower() in {"1", "true", "yes", "on"},
            },
        }
        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                socket_connect_timeout=2,
            )
            raw = r.get("vg:system_settings")
            r.close()
            if raw:
                import json
                data = json.loads(raw)
                if isinstance(data, dict):
                    merged = dict(defaults)
                    merged.update(data)
                    return merged
        except Exception as e:
            logger.debug(f"Failed to fetch system settings from Redis in clip recorder: {e}")

        try:
            row = await self.db.fetch_one("SELECT data FROM system_settings ORDER BY id DESC LIMIT 1")
            if row and row.get("data"):
                import json
                stored = row["data"]
                if isinstance(stored, str):
                    stored = json.loads(stored)
                if isinstance(stored, dict):
                    merged = dict(defaults)
                    merged.update(stored)
                    return merged
        except Exception as e:
            logger.error(f"Failed to fetch system settings in clip recorder: {e}")
        return defaults

    def _mask_faces(self, frame: 'cv2.Mat') -> 'cv2.Mat':
        """Blur all detected faces in the frame using OpenCV Haar Cascade."""
        if not hasattr(self, "_face_cascade"):
            try:
                self._face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            except Exception as e:
                logger.error(f"Failed to load Haar Cascade face classifier in clip recorder: {e}")
                self._face_cascade = None

        if not self._face_cascade or self._face_cascade.empty():
            return frame

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20))
            if len(faces) > 0:
                frame_copy = frame.copy()
                for (x, y, w, h) in faces:
                    face_roi = frame_copy[y:y+h, x:x+w]
                    ksize = int(max(15, (w // 2) | 1))
                    blurred = cv2.GaussianBlur(face_roi, (ksize, ksize), 0)
                    frame_copy[y:y+h, x:x+w] = blurred
                return frame_copy
        except Exception as e:
            logger.warning(f"Error in face masking: {e}")
        return frame

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_and_upload(
        self,
        event_id: str,
        event_type: str,
        camera_id: str,
        camera_source: str,
        detection_ts: float,
    ) -> Dict[str, Any]:
        """
        Full pipeline: record, upload, persist URLs.
        """
        result: Dict[str, Any] = {
            "snapshot_url": None,
            "clip_url": None,
            "snapshot_local": None,
            "clip_local": None,
            "clip_error": None,
        }

        logger.info(
            f"Starting clip pipeline for event {event_id}",
            extra={
                "event_type": event_type,
                "camera_id": camera_id,
                "camera_source": camera_source,
            },
        )

        # Step 1 — Find existing snapshot
        # Snapshot finding is just disk I/O, can stay sync or use to_thread
        snapshot_path = await asyncio.to_thread(self._find_snapshot, event_id, camera_id, event_type, detection_ts)
        result["snapshot_local"] = snapshot_path
        if snapshot_path:
            logger.info(f"Found snapshot: {snapshot_path}")
            # WRITE SNAPSHOT TO DB IMMEDIATELY (Instant feedback)
            try:
                await self._write_evidence(event_id, result)
            except Exception as e:
                logger.warning(f"Could not write snapshot evidence yet for {event_id}: {e} — will retry with clip")
                
            # Start Cloudinary upload of snapshot immediately, don't wait for clip!
            if self.config.cloudinary_configured:
                asyncio.create_task(self._upload_single_snapshot_task(event_id, event_type, snapshot_path, result))
        else:
            logger.warning(f"No matching snapshot found for event {event_id}")

        sys_settings = await self.get_system_settings()
        pre_seconds = sys_settings.get("clips", {}).get("preSeconds", self.config.clip_pre_seconds)
        post_seconds = sys_settings.get("clips", {}).get("postSeconds", self.config.clip_post_seconds)
        use_buffer = sys_settings.get("clips", {}).get("enableBackgroundBuffer", self.config.enable_background_buffer)

        # Step 2 — Record latency-aware post-event clip (This takes 10-15 seconds)
        # Recording uses OpenCV/FFMPEG, must be in a thread
        clip_path, error_msg = await asyncio.to_thread(
            self._record_clip, event_id, event_type, camera_source, detection_ts, pre_seconds, post_seconds, use_buffer
        )
        result["clip_local"] = clip_path
        
        if clip_path:
            logger.info(f"Clip recorded: {clip_path}")
            # WRITE CLIP TO DB IMMEDIATELY (Available before Cloud upload)
            try:
                await self._write_evidence(event_id, result)
            except Exception as e:
                logger.error(f"Failed to write clip evidence for {event_id}: {e}")
            await self._update_clip_status(event_id, "ready", None)
        else:
            # Use the intuitive error message from the recording attempt
            error_msg = error_msg or "Unknown Error"
            result["clip_error"] = error_msg
            await self._update_clip_status(event_id, "failed", error_msg)
            logger.warning(f"Clip recording failed for event {event_id}: {error_msg}")

        # Step 3 — Start background task for Cloudinary upload
        if self.config.cloudinary_configured:
            # We use an async task instead of a thread
            asyncio.create_task(self._upload_and_update_task(event_id, event_type, result))
            logger.info(f"Started background upload task for event {event_id}")

        logger.info(
            f"Local capture pipeline complete for event {event_id}. Cloud upload pending in background.",
            extra={
                "snapshot": result["snapshot_local"],
                "clip": result["clip_local"],
            },
        )

        return result

    async def _upload_single_snapshot_task(self, event_id: str, event_type: str, snapshot_path: str, result: Dict[str, Any]) -> None:
        """Background task to upload the snapshot to Cloudinary immediately."""
        try:
            if os.path.exists(snapshot_path):
                logger.info(f"Uploading snapshot to Cloudinary IMMEDIATELY: {snapshot_path}")
                snapshot_url = await asyncio.to_thread(self.uploader.upload_snapshot, snapshot_path, event_id, event_type)
                if snapshot_url:
                    result["snapshot_url"] = snapshot_url
                    await self._write_evidence(event_id, result)  # Update DB with cloud URL
                else:
                    logger.warning(f"Cloudinary snapshot upload failed for {event_id}")
            else:
                logger.warning(f"Snapshot file MISSING before immediate upload: {snapshot_path}")
        except Exception as e:
            logger.error(f"Error in immediate snapshot upload task for {event_id}: {e}")

    async def _upload_and_update_task(
        self,
        event_id: str,
        event_type: str,
        result: Dict[str, Any],
    ) -> None:
        """Background task to upload the clip to Cloudinary and update database records."""
        try:
            clip_path = result.get("clip_local")
            if clip_path and os.path.exists(clip_path):
                # Cloudinary upload is blocking I/O
                clip_url = await asyncio.to_thread(self.uploader.upload_clip, clip_path, event_id, event_type)
                if clip_url:
                    result["clip_url"] = clip_url
                    await self._write_evidence(event_id, result)  # Update DB with cloud URL
                    logger.info(f"Background upload successful for event {event_id}")
                else:
                    logger.warning(f"Background clip upload failed for event {event_id}")

        except Exception as e:
            logger.error(f"Error in background upload task for event {event_id}: {e}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _transcode_to_h264(self, filepath: str) -> bool:
        """Convert the mp4v file to a web-playable H.264 mp4 file."""
        temp_path = filepath + ".temp.mp4"
        try:
            cmd = [
                "ffmpeg", "-y", "-i", filepath,
                "-vcodec", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", temp_path
            ]
            process = subprocess.run(cmd, capture_output=True, text=True)
            if process.returncode != 0:
                raise Exception(f"ffmpeg failed with exit code {process.returncode}. Stderr: {process.stderr}")
            
            os.replace(temp_path, filepath)
            logger.info(f"Successfully transcoded {filepath} to H.264")
            return True
        except Exception as e:
            logger.error(f"Failed to transcode {filepath} to H.264: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False

    def _find_snapshot(
        self,
        event_id: str,
        camera_id: str,
        event_type: str,
        detection_ts: float,
    ) -> Optional[str]:
        """
        Find the closest snapshot saved by the AI worker at detection time.

        The AI worker saves files as: <event_type>_<camera_id>_<ts_ms>.jpg
        We look for files whose millisecond timestamp is within 10 seconds
        of detection_ts.

        Args:
            camera_id:    Camera identifier
            event_type:   weapon | fire | fall
            detection_ts: Unix epoch seconds of the detection

        Returns:
            Full path to the best matching snapshot, or None
        """
        try:
            snapshot_dir = Path(self.config.snapshot_dir)
            if not snapshot_dir.exists():
                return None

            # Remove '_detected' suffix to match AI worker filename format (e.g. weapon_detected -> weapon)
            model_type = event_type.replace('_detected', '')
            # Expected prefix: <model_type>_<camera_id>_
            prefix = f"{model_type}_{camera_id}_"
            detection_ts_ms = detection_ts * 1000
            tolerance_ms = 30 * 1000  # 30 seconds

            best_path: Optional[str] = None
            best_diff = float("inf")

            match_attempts = 0
            for f in snapshot_dir.iterdir():
                if not f.name.endswith(".jpg"):
                    continue
                
                match_attempts += 1
                
                # Flexible matching: handle fire vs fire_detected and case sensitivity
                filename_lower = f.name.lower()
                prefix_lower = prefix.lower()
                alt_prefix_lower = prefix_lower.replace("_detected", "")
                
                is_match = filename_lower.startswith(prefix_lower) or filename_lower.startswith(alt_prefix_lower)
                
                if not is_match:
                    if match_attempts <= 10:
                        logger.debug(f"Snapshot mismatch: {f.name} doesn't match {prefix} or {alt_prefix_lower}")
                    continue
                
                # Filename: <type>_<cam>_<ts_ms>.jpg
                # Extract timestamp part
                stem = f.stem  # e.g. weapon_cam1_1711000000123
                parts = stem.rsplit("_", 1)
                if len(parts) != 2:
                    continue
                try:
                    file_ts_ms = float(parts[1])
                except ValueError:
                    continue

                diff = abs(file_ts_ms - detection_ts_ms)
                if diff <= tolerance_ms and diff < best_diff:
                    best_diff = diff
                    best_path = str(f)

            if best_path:
                logger.info(f"Found best snapshot match for {event_id}: {os.path.basename(best_path)} (diff: {best_diff/1000:.2f}s)")
                # Secure the snapshot from being deleted by the AI Worker's rolling buffer
                try:
                    import shutil
                    safe_path = os.path.join(str(snapshot_dir), f"snapshot_secured_{event_id}.jpg")
                    shutil.copy2(best_path, safe_path)
                    best_path = safe_path
                except Exception as e:
                    logger.error(f"Could not secure snapshot copy: {e}")
            else:
                logger.warning(f"No snapshot found within {tolerance_ms/1000}s for {event_id}")

            return best_path

        except Exception as e:
            logger.error(f"Error finding snapshot: {e}")
            return None

    def _record_clip(
        self,
        event_id: str,
        event_type: str,
        camera_source: str,
        detection_ts: float,
        pre_seconds: int = None,
        post_seconds: int = None,
        use_buffer: bool = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Record a post-event video clip using the Latency-Aware Ring Buffer.

        Extracts frames corresponding to [detection_ts - pre_seconds, detection_ts + post_seconds]
        from the background rolling buffer. If the buffer doesn't have it (or camera isn't tracked),
        starts tracking.

        Args:
            event_id:      UUID (used in output filename)
            event_type:    weapon | fire | fall
            camera_source: Camera stream URL
            detection_ts:  Original Unix timestamp of the detection

        Returns:
            Path to the saved .mp4 file, or None on failure
        """
        try:
            if pre_seconds is None: pre_seconds = self.config.clip_pre_seconds
            if post_seconds is None: post_seconds = self.config.clip_post_seconds
            if use_buffer is None: use_buffer = self.config.enable_background_buffer

            if not use_buffer:
                return self._record_clip_direct(event_id, event_type, camera_source, detection_ts, pre_seconds, post_seconds)

            # Ensure the background buffer is running for this camera
            self._start_camera_buffer(camera_source)

            # FIX: Use the REAL shared lock, not a brand-new temporary one
            lock = self.buffer_locks.get(camera_source)
            if lock is None:
                logger.warning(f"No buffer lock found for {camera_source} — falling back to direct recording")
                return self._record_clip_direct(event_id, event_type, camera_source, detection_ts, pre_seconds, post_seconds)

            with lock:
                if camera_source not in self.frame_buffers:
                    logger.warning(f"No frame buffer found for {camera_source} — falling back to direct recording")
                    return self._record_clip_direct(event_id, event_type, camera_source, detection_ts, pre_seconds, post_seconds)
                buffer_snapshot = list(self.frame_buffers[camera_source])
                
            if not buffer_snapshot:
                logger.warning(f"Ring buffer is empty for {camera_source} — falling back to direct recording")
                # We try direct recording, but if it's because the camera is offline, _record_clip_direct will tell us
                return self._record_clip_direct(event_id, event_type, camera_source, detection_ts, pre_seconds, post_seconds)
                
            # Define exact temporal window
            start_ts = detection_ts - pre_seconds
            end_ts = detection_ts + post_seconds
            
            # Extract matching frames
            valid_frames = []
            for ts, frame in buffer_snapshot:
                if start_ts <= ts <= end_ts:
                    valid_frames.append(frame)
                    
            if not valid_frames:
                logger.warning(
                    f"No frames matched time window [{start_ts:.1f}, {end_ts:.1f}] "
                    f"(buffer has {len(buffer_snapshot)} frames) — Event might be too old"
                )
                # If frames exist in buffer but none match, the event is likely a backlog catch-up
                if len(buffer_snapshot) > 0:
                    return None, ClipError.TOO_OLD
                
                return self._record_clip_direct(event_id, event_type, camera_source, detection_ts, pre_seconds, post_seconds)

            # Fetch settings to check if face masking is enabled
            mask_faces = False
            try:
                mask_faces = self._get_mask_faces_setting()
            except Exception as se:
                logger.warning(f"Failed to check privacy settings in stitching: {se}")

            height, width = valid_frames[0].shape[:2]
            fps = self.config.camera_fps

            ts_str = int(detection_ts)
            filename = f"{event_type}_{event_id}_{ts_str}.mp4"
            out_path = os.path.join(self.config.clip_dir, filename)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

            logger.info(
                f"Stitching {len(valid_frames)} buffered frames for clip "
                f"[window: {pre_seconds}s pre + {post_seconds}s post]",
                extra={"event_id": event_id, "output": out_path},
            )

            for frame in valid_frames:
                if mask_faces:
                    frame = self._mask_faces(frame)
                writer.write(frame)
            writer.release()
            
            if not self._transcode_to_h264(out_path):
                return out_path, ClipError.TRANSCODE
                
            return out_path, None
            
        except Exception as e:
            logger.error(f"Error recording latency-aware clip: {e}", exc_info=True)
            logger.warning(f"Falling back to direct recording after exception for event {event_id}")
            return self._record_clip_direct(event_id, event_type, camera_source, detection_ts, pre_seconds, post_seconds)

    def _record_clip_direct(
        self,
        event_id: str,
        event_type: str,
        camera_source: str,
        detection_ts: float,
        pre_seconds: int = None,
        post_seconds: int = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Record a clip directly from source without persistent background buffer."""
        cap = None
        writer = None
        try:
            cap = cv2.VideoCapture(camera_source)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                logger.error(f"Direct clip capture failed to open source: {camera_source}")
                return None, ClipError.OFFLINE

            ok, first_frame = cap.read()
            if not ok or first_frame is None:
                logger.error(f"Direct clip capture could not read first frame: {camera_source}")
                return None, ClipError.NO_SIGNAL

            # Fetch settings to check if face masking is enabled
            mask_faces = False
            try:
                mask_faces = self._get_mask_faces_setting()
            except Exception as se:
                logger.warning(f"Failed to check privacy settings in direct record: {se}")

            if pre_seconds is None: pre_seconds = self.config.clip_pre_seconds
            if post_seconds is None: post_seconds = self.config.clip_post_seconds

            height, width = first_frame.shape[:2]
            fps = self.config.camera_fps
            # If buffer is off, we can't go back in time, but we should still record the requested total duration
            total_duration = pre_seconds + post_seconds
            if total_duration <= 0:
                total_duration = self.config.clip_pre_seconds + self.config.clip_post_seconds
                if total_duration <= 0:
                    total_duration = 10  # Ultimate safety fallback
            total_frames = max(1, int(total_duration * fps))

            ts_str = int(detection_ts)
            filename = f"{event_type}_{event_id}_{ts_str}.mp4"
            out_path = os.path.join(self.config.clip_dir, filename)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

            if mask_faces:
                first_frame = self._mask_faces(first_frame)
            writer.write(first_frame)
            frames_written = 1

            start_time = time.time()
            max_wait_time = total_duration * 1.5 + 10  # Generous timeout for laggy IP cameras

            while frames_written < total_frames:
                if time.time() - start_time > max_wait_time:
                    logger.warning(f"Direct recording timed out after {max_wait_time}s. Captured {frames_written}/{total_frames} frames.")
                    break
                    
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if mask_faces:
                    frame = self._mask_faces(frame)
                writer.write(frame)
                frames_written += 1

            logger.info(
                "Direct clip recording completed",
                extra={
                    "event_id": event_id,
                    "frames_written": frames_written,
                    "target_frames": total_frames,
                    "output": out_path,
                },
            )
            
            if writer:
                writer.release()
                writer = None
            if cap:
                cap.release()
                cap = None
                
            if not self._transcode_to_h264(out_path):
                return out_path, ClipError.TRANSCODE

            return out_path, None

        except Exception as e:
            logger.error(f"Error in direct clip recording: {e}", exc_info=True)
            return None, ClipError.INTERNAL
        finally:
            if writer:
                writer.release()
            if cap:
                cap.release()

    async def _write_evidence(
        self,
        event_id: str,
        result: Dict[str, Any],
    ) -> None:
        """
        Write evidence to database. Handles both initial local write and cloud updates.
        """
        snapshot_url = result.get("snapshot_url")
        clip_url = result.get("clip_url")
        snapshot_local = result.get("snapshot_local")
        clip_local = result.get("clip_local")

        # Determine Snapshot URL and Provider
        if snapshot_url:
            final_snapshot = snapshot_url
            provider_snap = "cloudinary"
        elif snapshot_local:
            final_snapshot = snapshot_local
            provider_snap = "local"
        else:
            final_snapshot = None
            provider_snap = None

        # Determine Clip URL and Provider
        if clip_url:
            final_clip = clip_url
            provider_clip = "cloudinary"
        elif clip_local:
            final_clip = clip_local
            provider_clip = "local"
        else:
            final_clip = None
            provider_clip = None

        now = time.time()
        
        try:
            # Process Snapshot
            if final_snapshot:
                row = await self.db.fetch_one(
                    "SELECT id FROM event_evidence WHERE event_id = $1 AND evidence_type = $2",
                    event_id, "snapshot"
                )
                
                if row:
                    await self.db.execute(
                        "UPDATE event_evidence SET storage_provider = $1, public_url = $2 WHERE id = $3",
                        provider_snap, final_snapshot, row['id']
                    )
                else:
                    await self.db.execute(
                        """
                        INSERT INTO event_evidence
                            (id, event_id, evidence_type, storage_provider, public_url, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        str(uuid.uuid4()), event_id, "snapshot", provider_snap, final_snapshot, now
                    )

            # Process Clip
            if final_clip:
                row = await self.db.fetch_one(
                    "SELECT id FROM event_evidence WHERE event_id = $1 AND evidence_type = $2",
                    event_id, "clip"
                )
                
                if row:
                    await self.db.execute(
                        "UPDATE event_evidence SET storage_provider = $1, public_url = $2 WHERE id = $3",
                        provider_clip, final_clip, row['id']
                    )
                else:
                    await self.db.execute(
                        """
                        INSERT INTO event_evidence
                            (id, event_id, evidence_type, storage_provider, public_url, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        str(uuid.uuid4()), event_id, "clip", provider_clip, final_clip, now
                    )
        except Exception as e:
            logger.error(f"PostgreSQL Error for event {event_id}: {e}")
            raise

    async def _update_clip_status(
        self,
        event_id: str,
        status: str,
        error: Optional[str],
    ) -> None:
        """Update clip lifecycle status on events table."""
        try:
            await self.db.execute(
                """
                UPDATE events
                SET clip_status = $1, clip_error = $2, clip_updated_at = $3
                WHERE id = $4
                """,
                status, error, time.time(), event_id
            )
        except Exception as e:
            logger.warning(f"Failed to update clip status for event {event_id}: {e}")