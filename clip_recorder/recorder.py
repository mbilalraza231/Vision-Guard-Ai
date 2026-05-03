"""
VisionGuard AI - Clip Recorder

Records post-event video clips, finds matching snapshots, uploads both
to Cloudinary, and writes the resulting URLs to the event_evidence table.

Completely isolated from inference pipeline — runs as a separate process.
"""

import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

import threading
from collections import deque

import cv2
import subprocess

from .config import ClipConfig
from .uploader import CloudinaryUploader

logger = logging.getLogger(__name__)


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

        # Ensure local directories exist
        os.makedirs(config.clip_dir, exist_ok=True)
        os.makedirs(config.snapshot_dir, exist_ok=True)

        logger.info(
            "ClipRecorder initialized",
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
            
        # Store ~20 seconds of video dynamically
        max_buffer_frames = self.config.camera_fps * 20 
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
        """Continuously reads from RTSP into the ring buffer."""
        logger.info(f"Starting background ring buffer for {camera_source}")
        cap = None
        
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
                
                ret, frame = cap.read()
                if not ret or frame is None:
                    cap.release()
                    cap = None
                    continue
                
                ts = time.time()
                with self.buffer_locks[camera_source]:
                    self.frame_buffers[camera_source].append((ts, frame))
                    
                # Throttle slightly to target fps
                time.sleep(1.0 / self.config.camera_fps)
                
            except Exception as e:
                logger.error(f"Error in ring buffer capture for {camera_source}: {e}")
                time.sleep(2.0)
                
        if cap:
            cap.release()
            
    def shutdown(self):
        """Stops the background capture threads."""
        self._shutdown_event.set()
        for t in self._capture_threads.values():
            t.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_and_upload(
        self,
        event_id: str,
        event_type: str,
        camera_id: str,
        camera_source: str,
        detection_ts: float,
    ) -> Dict[str, Any]:
        """
        Full pipeline: record, upload, persist URLs.

        Args:
            event_id:      UUID of the classified event (from events table)
            event_type:    weapon | fire | fall
            camera_id:     Camera identifier
            camera_source: RTSP / HTTP URL of the camera stream
            detection_ts:  Unix timestamp (seconds) of the detection

        Returns:
            dict with keys: snapshot_url, clip_url, snapshot_local, clip_local
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
        snapshot_path = self._find_snapshot(camera_id, event_type, detection_ts)
        result["snapshot_local"] = snapshot_path
        if snapshot_path:
            logger.info(f"Found snapshot: {snapshot_path}")
            # WRITE SNAPSHOT TO DB IMMEDIATELY (Instant feedback)
            self._write_evidence(event_id, result)
        else:
            logger.warning(f"No matching snapshot found for event {event_id}")

        # Step 2 — Record latency-aware post-event clip (This takes 10-15 seconds)
        clip_path = self._record_clip(event_id, event_type, camera_source, detection_ts)
        result["clip_local"] = clip_path
        if clip_path:
            logger.info(f"Clip recorded: {clip_path}")
            # WRITE CLIP TO DB IMMEDIATELY (Available before Cloud upload)
            self._write_evidence(event_id, result)
            self._update_clip_status(event_id, "ready", None)
        else:
            result["clip_error"] = "clip_record_failed"
            self._update_clip_status(event_id, "failed", "clip_record_failed")
            logger.warning(f"Clip recording failed or skipped for event {event_id}")

        # Step 3 — Start background thread for Cloudinary upload
        if self.config.cloudinary_configured:
            threading.Thread(
                target=self._upload_and_update_task,
                args=(event_id, event_type, result),
                daemon=True,
                name=f"Upload-{event_id[:8]}"
            ).start()
            logger.info(f"Started background upload task for event {event_id}")

        logger.info(
            f"Local capture pipeline complete for event {event_id}. Cloud upload pending in background.",
            extra={
                "snapshot": result["snapshot_local"],
                "clip": result["clip_local"],
            },
        )

        return result

    def _upload_and_update_task(
        self,
        event_id: str,
        event_type: str,
        result: Dict[str, Any],
    ) -> None:
        """Background task to upload to Cloudinary and update database records."""
        try:
            snapshot_path = result.get("snapshot_local")
            clip_path = result.get("clip_local")
            
            # 1. Upload Snapshot
            if snapshot_path and os.path.exists(snapshot_path):
                snapshot_url = self.uploader.upload_snapshot(
                    snapshot_path, event_id, event_type
                )
                if snapshot_url:
                    result["snapshot_url"] = snapshot_url
                    self._write_evidence(event_id, result)  # Update DB with cloud URL

            # 2. Upload Clip
            if clip_path and os.path.exists(clip_path):
                clip_url = self.uploader.upload_clip(
                    clip_path, event_id, event_type
                )
                if clip_url:
                    result["clip_url"] = clip_url
                    self._write_evidence(event_id, result)  # Update DB with cloud URL
                    logger.info(f"Background upload successful for event {event_id}")
                else:
                    logger.warning(f"Background clip upload failed for event {event_id}")

        except Exception as e:
            logger.error(f"Error in background upload task for event {event_id}: {e}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _transcode_to_h264(self, filepath: str) -> None:
        """Convert the mp4v file to a web-playable H.264 mp4 file."""
        temp_path = filepath + ".temp.mp4"
        try:
            cmd = [
                "ffmpeg", "-y", "-i", filepath,
                "-vcodec", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", temp_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.replace(temp_path, filepath)
            logger.info(f"Successfully transcoded {filepath} to H.264")
        except Exception as e:
            logger.error(f"Failed to transcode {filepath} to H.264: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _find_snapshot(
        self,
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
            tolerance_ms = 10 * 1000  # 10 seconds

            best_path: Optional[str] = None
            best_diff = float("inf")

            for f in snapshot_dir.iterdir():
                if not (f.name.startswith(prefix) and f.name.endswith(".jpg")):
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
    ) -> Optional[str]:
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
            if not self.config.enable_background_buffer:
                return self._record_clip_direct(event_id, event_type, camera_source)

            # Ensure the background buffer is running for this camera
            self._start_camera_buffer(camera_source)
            
            # Wait briefly to let the buffer build if it was just started or if the detection 
            # literally just happened, to ensure we get some "post" frames.
            # In a heavy latency scenario, the detection_ts is already 10 seconds in the past!
            # But if processing is extremely fast, we might need to wait for post_frames to arrive.
            time.sleep(2.0)
            
            with self.buffer_locks.get(camera_source, threading.Lock()):
                if camera_source not in self.frame_buffers:
                    return None
                buffer_snapshot = list(self.frame_buffers[camera_source])
                
            if not buffer_snapshot:
                logger.error(f"No frames in ring buffer for {camera_source}")
                return None
                
            # Define exact temporal window
            start_ts = detection_ts - self.config.clip_pre_seconds
            end_ts = detection_ts + self.config.clip_post_seconds
            
            # Extract matching frames
            valid_frames = []
            for ts, frame in buffer_snapshot:
                if start_ts <= ts <= end_ts:
                    valid_frames.append(frame)
                    
            if not valid_frames:
                logger.warning(
                    f"No frames matched time window [{start_ts}, {end_ts}] in buffer for {camera_source}"
                )
                return None

            height, width = valid_frames[0].shape[:2]
            fps = self.config.camera_fps

            ts_str = int(time.time())
            filename = f"{event_type}_{event_id}_{ts_str}.mp4"
            out_path = os.path.join(self.config.clip_dir, filename)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

            logger.info(
                f"Stitching {len(valid_frames)} buffered frames for clip",
                extra={"event_id": event_id, "output": out_path},
            )

            for frame in valid_frames:
                writer.write(frame)
            writer.release()
            
            self._transcode_to_h264(out_path)
            return out_path
            
        except Exception as e:
            logger.error(f"Error recording latency-aware clip: {e}", exc_info=True)
            return None

    def _record_clip_direct(
        self,
        event_id: str,
        event_type: str,
        camera_source: str,
    ) -> Optional[str]:
        """Record a clip directly from source without persistent background buffer."""
        cap = None
        writer = None
        try:
            cap = cv2.VideoCapture(camera_source)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                logger.error(f"Direct clip capture failed to open source: {camera_source}")
                return None

            ok, first_frame = cap.read()
            if not ok or first_frame is None:
                logger.error(f"Direct clip capture could not read first frame: {camera_source}")
                return None

            height, width = first_frame.shape[:2]
            fps = self.config.camera_fps
            total_frames = max(1, int(self.config.clip_post_seconds * fps))

            ts_str = int(time.time())
            filename = f"{event_type}_{event_id}_{ts_str}.mp4"
            out_path = os.path.join(self.config.clip_dir, filename)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

            writer.write(first_frame)
            frames_written = 1

            while frames_written < total_frames:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
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
                
            self._transcode_to_h264(out_path)
            return out_path

        except Exception as e:
            logger.error(f"Error in direct clip recording: {e}", exc_info=True)
            return None
        finally:
            if writer:
                writer.release()
            if cap:
                cap.release()

    def _write_evidence(
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

        # Prioritize cloud URLs if they exist
        final_snapshot = snapshot_url or snapshot_local
        final_clip = clip_url or clip_local

        if not final_snapshot and not final_clip:
            return

        try:
            conn = sqlite3.connect(self.config.db_path)
            conn.execute("PRAGMA foreign_keys=ON;")
            cursor = conn.cursor()
            now = time.time()

            # Process Snapshot
            if final_snapshot:
                provider = "cloudinary" if snapshot_url else "local"
                # Check if record already exists for this (event_id, evidence_type)
                cursor.execute(
                    "SELECT id FROM event_evidence WHERE event_id = ? AND evidence_type = ?",
                    (event_id, "snapshot")
                )
                row = cursor.fetchone()
                
                if row:
                    # Update existing record (promote local to cloud)
                    cursor.execute(
                        "UPDATE event_evidence SET storage_provider = ?, public_url = ? WHERE id = ?",
                        (provider, final_snapshot, row[0])
                    )
                else:
                    # Insert new record
                    cursor.execute(
                        """
                        INSERT INTO event_evidence
                            (id, event_id, evidence_type, storage_provider, public_url, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid.uuid4()), event_id, "snapshot", provider, final_snapshot, now),
                    )
                logger.info(
                    f"Snapshot evidence {provider} updated for event {event_id}",
                    extra={"url": final_snapshot},
                )

            # Process Clip
            if final_clip:
                provider = "cloudinary" if clip_url else "local"
                cursor.execute(
                    "SELECT id FROM event_evidence WHERE event_id = ? AND evidence_type = ?",
                    (event_id, "clip")
                )
                row = cursor.fetchone()
                
                if row:
                    cursor.execute(
                        "UPDATE event_evidence SET storage_provider = ?, public_url = ? WHERE id = ?",
                        (provider, final_clip, row[0])
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO event_evidence
                            (id, event_id, evidence_type, storage_provider, public_url, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid.uuid4()), event_id, "clip", provider, final_clip, now),
                    )
                logger.info(
                    f"Clip evidence {provider} updated for event {event_id}",
                    extra={"url": final_clip},
                )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to write evidence for event {event_id}: {e}")

    def _update_clip_status(
        self,
        event_id: str,
        status: str,
        error: Optional[str],
    ) -> None:
        """Update clip lifecycle status on events table (best-effort, retried)."""
        attempts = 8
        delay_sec = 0.5

        for attempt in range(1, attempts + 1):
            try:
                conn = sqlite3.connect(self.config.db_path)
                conn.execute("PRAGMA foreign_keys=ON;")
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE events
                    SET clip_status = ?, clip_error = ?, clip_updated_at = ?
                    WHERE id = ?
                    """,
                    (status, error, time.time(), event_id),
                )
                conn.commit()
                updated = cursor.rowcount
                conn.close()

                if updated > 0:
                    return

                if attempt < attempts:
                    time.sleep(delay_sec)

            except Exception as e:
                logger.warning(
                    f"Failed to update clip status for event {event_id}: {e}",
                    extra={"event_id": event_id, "status": status, "attempt": attempt},
                )
                if attempt < attempts:
                    time.sleep(delay_sec)

        logger.warning(
            f"Clip status update skipped (event not found yet): {event_id}",
            extra={"status": status},
        )
