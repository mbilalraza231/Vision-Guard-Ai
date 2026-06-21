"""
VisionGuard AI - Camera Process

Single camera process logic.
Runs in dedicated OS process for isolation and stability.
"""

import time
import signal
import logging
from multiprocessing import Process, Event
from typing import Optional
from ..config import CameraConfig, RedisConfig, BufferConfig, RetryConfig, SharedMemoryConfig
from ..capture.rtsp_handler import RTSPHandler
from ..capture.frame_grabber import FrameGrabber
from ..detection.motion_detector import MotionDetector
from ..redis_queue.redis_producer import RedisProducer
from ..redis_queue.task_models import TaskMetadata
from ..storage.shared_memory_impl import SharedMemoryImpl
from ..utils.logging import setup_logging


class CameraProcess:
    """
    Single camera capture process.
    
    Main loop:
    1. Connect to RTSP stream
    2. Grab frame at configured FPS
    3. Run motion detection
    4. If motion detected:
       - Write frame to shared memory
       - Enqueue task to Redis
    5. Handle errors (reconnect, skip, log)
    """
    
    def __init__(
        self,
        camera_config: CameraConfig,
        redis_config: RedisConfig,
        buffer_config: BufferConfig,
        retry_config: RetryConfig,
        shared_memory_config: SharedMemoryConfig,
        log_level: str = "INFO",
        log_format: str = "json"
    ):
        """
        Initialize camera process.
        
        Args:
            camera_config: Camera configuration
            redis_config: Redis configuration
            buffer_config: Buffer configuration
            retry_config: Retry configuration
            shared_memory_config: Shared memory configuration
            log_level: Log level
            log_format: Log format (json/text)
        """
        self.camera_config = camera_config
        self.redis_config = redis_config
        self.buffer_config = buffer_config
        self.retry_config = retry_config
        self.shared_memory_config = shared_memory_config
        self.log_level = log_level
        self.log_format = log_format
        
        # Process control
        self.process: Optional[Process] = None
        self.stop_event = Event()
        
        # Components (initialized in process)
        self.rtsp_handler: Optional[RTSPHandler] = None
        self.frame_grabber: Optional[FrameGrabber] = None
        self.motion_detector: Optional[MotionDetector] = None
        self.redis_producer: Optional[RedisProducer] = None
        self.shared_memory: Optional[SharedMemoryImpl] = None
        self.logger: Optional[logging.Logger] = None
    
    def start(self) -> bool:
        """
        Start camera process.
        
        Returns:
            True if process started successfully
        """
        self.stop_event.clear()
        
        self.process = Process(
            target=self._run,
            name=f"CameraProcess-{self.camera_config.camera_id}",
            daemon=False
        )
        self.process.start()
        
        return self.process.is_alive()
    
    def stop(self, timeout: float = 10.0) -> None:
        """
        Stop camera process gracefully.
        
        Args:
            timeout: Maximum time to wait for process to stop
        """
        if not self.process:
            return
        
        # Signal process to stop
        self.stop_event.set()
        
        # Wait for process to finish
        self.process.join(timeout=timeout)
        
        # Force terminate if still alive
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2.0)
        
        # Force kill if still alive
        if self.process.is_alive():
            self.process.kill()
            self.process.join()
    
    def is_alive(self) -> bool:
        """Check if process is alive."""
        return self.process is not None and self.process.is_alive()
    
    def _run(self) -> None:
        """
        Main process loop (runs in separate process).
        
        This is the entry point for the camera process.
        """
        # Setup logging for this process
        self.logger = setup_logging(
            level=self.log_level,
            format_type=self.log_format,
            camera_id=self.camera_config.camera_id
        )
        
        self.logger.info(
            f"Camera process starting",
            extra={"camera_id": self.camera_config.camera_id}
        )
        
        try:
            # Initialize components
            if not self._initialize():
                self.logger.error("Failed to initialize camera process")
                return
            
            # Main capture loop
            self._capture_loop()
            
        except Exception as e:
            self.logger.error(
                f"Fatal error in camera process: {e}",
                extra={"error": str(e)}
            )
        finally:
            # Cleanup
            self._shutdown()
    
    def _initialize(self) -> bool:
        """
        Initialize all components.
        
        Returns:
            True if initialization successful
        """
        try:
            # Initialize RTSP handler
            self.rtsp_handler = RTSPHandler(
                rtsp_url=self.camera_config.rtsp_url,
                camera_id=self.camera_config.camera_id,
                retry_config=self.retry_config
            )
            
            # Initial RTSP connect (non-fatal).
            # If stream is temporarily unavailable, keep process alive and
            # let capture loop auto-reconnect continuously.
            if not self.rtsp_handler.connect():
                self.logger.warning(
                    "Initial RTSP connect failed; camera process will keep retrying in background"
                )
            
            # Initialize frame grabber
            self.frame_grabber = FrameGrabber(
                fps=self.camera_config.fps,
                camera_id=self.camera_config.camera_id
            )
            
            # Initialize motion detector
            self.motion_detector = MotionDetector(
                threshold=self.camera_config.motion_threshold
            )
            
            # Initialize shared memory
            self.shared_memory = SharedMemoryImpl(
                max_frame_size_mb=self.shared_memory_config.max_frame_size_mb
            )
            
            # Initialize Redis producer
            self.redis_producer = RedisProducer(
                redis_config=self.redis_config,
                buffer_config=self.buffer_config,
                camera_id=self.camera_config.camera_id
            )
            
            # Connect to Redis
            self.redis_producer.connect()
            
            self.logger.info("Camera process initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(
                f"Initialization failed: {e}",
                extra={"error": str(e)}
            )
            return False
    
    def _capture_loop(self) -> None:
        """Main capture loop."""
        self.logger.info("Starting capture loop")
        
        consecutive_read_failures = 0
        consecutive_loop_errors = 0
        frames_processed = 0
        last_heartbeat = time.time()
        heartbeat_interval_sec = 30.0
        reconnect_attempts = 0
        reconnect_backoff = self.retry_config.initial_backoff_seconds
        
        while not self.stop_event.is_set():
            try:
                # Check if we should capture this frame (FPS throttling)
                if not self.frame_grabber.should_capture():
                    time.sleep(0.01)  # Small sleep to prevent busy waiting
                    continue

                # Keep camera process alive and continuously attempt reconnect
                # when stream is unavailable.
                if self.rtsp_handler and not self.rtsp_handler.is_connected:
                    # Check if this is a local file. If it is, and we lost connection
                    # (either reached the end, or file not found), we should stop gracefully 
                    # instead of reconnecting infinitely.
                    source_url = getattr(self.rtsp_handler, 'rtsp_url', '')
                    is_local_file = source_url and not source_url.lower().startswith(('http://', 'https://', 'rtsp://', 'rtmp://'))
                    if is_local_file:
                        self.logger.info("Local video file ended or not found. Stopping capture and notifying backend.", extra={"camera_id": self.camera_config.camera_id})
                        
                        # Notify backend to disable the camera so it doesn't auto-restart infinitely
                        try:
                            import urllib.request
                            import os
                            backend_host = os.getenv("BACKEND_HOST", "backend")
                            backend_port = os.getenv("BACKEND_PORT", "8000")
                            url = f"http://{backend_host}:{backend_port}/cameras/{self.camera_config.camera_id}/stop"
                            req = urllib.request.Request(url, method="POST")
                            urllib.request.urlopen(req, timeout=5.0)
                            self.logger.info("Successfully notified backend to stop local video camera.")
                        except Exception as e:
                            self.logger.error(f"Failed to notify backend to stop camera: {e}")
                            
                        self.stop_event.set()
                        break

                    if self.rtsp_handler.reconnect():
                        reconnect_attempts = 0
                        reconnect_backoff = self.retry_config.initial_backoff_seconds
                        consecutive_read_failures = 0
                        self.logger.info("Camera stream reconnected")
                    else:
                        reconnect_attempts += 1
                        sleep_seconds = min(reconnect_backoff, self.retry_config.max_backoff_seconds)
                        self.logger.warning(
                            "Camera stream unavailable; will retry reconnect",
                            extra={
                                "reconnect_attempt": reconnect_attempts,
                                "sleep_seconds": sleep_seconds,
                            },
                        )
                        time.sleep(sleep_seconds)
                        reconnect_backoff = min(
                            reconnect_backoff * self.retry_config.backoff_multiplier,
                            self.retry_config.max_backoff_seconds,
                        )
                    continue
                
                # Read frame from RTSP stream
                frame = self.rtsp_handler.read_frame()
                
                if frame is None:
                    # Stream likely dropped mid-run.
                    # If this is a local file, we just reached the end of the video. Break the loop.
                    source_url = getattr(self.rtsp_handler, 'rtsp_url', '')
                    is_local_file = source_url and not source_url.lower().startswith(('http://', 'https://', 'rtsp://'))
                    if is_local_file:
                        self.logger.info("Local video file reached the end. Stopping capture.", extra={"camera_id": self.camera_id})
                        self.stop_event.set()
                        break

                    # Otherwise, mark disconnected and let reconnect branch handle recovery attempts.
                    consecutive_read_failures += 1
                    if consecutive_read_failures % 5 == 0:
                        self.logger.warning(
                            "Consecutive frame read failures",
                            extra={"consecutive_read_failures": consecutive_read_failures},
                        )
                    self.rtsp_handler.disconnect()
                    continue
                
                # Reset failure counter on successful read
                consecutive_read_failures = 0
                consecutive_loop_errors = 0
                reconnect_attempts = 0
                reconnect_backoff = self.retry_config.initial_backoff_seconds
                
                # Mark frame as captured
                self.frame_grabber.mark_captured()
                
                # Report real FPS to Redis every 5 seconds (must be before motion detection continue)
                now = time.time()
                if now - last_heartbeat >= 5.0:
                    stats = self.frame_grabber.get_stats()
                    actual_fps = stats.get("actual_fps", 0.0)
                    
                    # Store in Redis for the backend to read
                    if self.redis_producer and self.redis_producer.client:
                        try:
                            # Key format: vg:metrics:camera:{camera_id}:fps
                            fps_key = f"vg:metrics:camera:{self.camera_config.camera_id}:fps"
                            self.redis_producer.client.setex(fps_key, 15, str(actual_fps))
                        except Exception:
                            pass
                            
                    self.logger.debug(
                        "Camera heartbeat",
                        extra={
                            "fps": actual_fps,
                            "frames_processed": frames_processed,
                            "is_connected": self.rtsp_handler.is_connected if self.rtsp_handler else False,
                        }
                    )
                    last_heartbeat = now
                
                # Run motion detection (only if enabled)
                if hasattr(self.camera_config, 'motion_enabled') and self.camera_config.motion_enabled:
                    has_motion = self.motion_detector.detect(frame)
                    
                    if not has_motion:
                        # No motion, skip frame
                        continue
                
                # Motion detected (or motion detection disabled) - process frame
                self._process_frame(frame)
                frames_processed += 1
                
                # Log progress every 10 frames at INFO level
                if frames_processed % 10 == 0:
                    self.logger.info(
                        f"Capture loop progress: {frames_processed} frames processed",
                        extra={"frames_processed": frames_processed}
                    )
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(
                    f"Error in capture loop: {e}",
                    extra={"error": str(e)}
                )
                consecutive_loop_errors += 1
                sleep_seconds = min(
                    self.retry_config.initial_backoff_seconds * max(1, consecutive_loop_errors),
                    self.retry_config.max_backoff_seconds,
                )
                time.sleep(sleep_seconds)
        
        self.logger.info(f"Capture loop ended after {frames_processed} frames")
    
    def _process_frame(self, frame) -> None:
        """
        Process frame with motion detected.
        
        Publishes to ALL priority queues so each worker model
        (weapon/fire/fall) processes every frame.
        
        Args:
            frame: Frame to process
        """
        try:
            # Write frame to shared memory (with optional compression)
            compressed_bytes = None
            pre_resize_dict = None
            if getattr(self.camera_config, 'enable_frame_compression', False):
                try:
                    import sys
                    import os
                    # Ensure project root is in sys.path
                    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                    from preprocessing.resize_and_compress import (
                        compress_frame, resize_and_compress_frame, apply_enhancements
                    )

                    _enable_clahe = getattr(self.camera_config, 'enable_clahe', False)
                    _enable_denoising = getattr(self.camera_config, 'enable_denoising', False)
                    _fmt = getattr(self.camera_config, 'compression_format', 'jpeg')
                    _quality = getattr(self.camera_config, 'compression_quality', 95)

                    # Apply enhancements once at full resolution (if any are enabled)
                    enhanced_frame = apply_enhancements(
                        frame,
                        enable_clahe=_enable_clahe,
                        enable_denoising=_enable_denoising,
                    ) if (_enable_clahe or _enable_denoising) else frame

                    # 1. Compress base (enhanced) frame
                    compressed_bytes = compress_frame(
                        enhanced_frame,
                        format=_fmt,
                        quality=_quality,
                    )

                    # 2. Generate pre-resized variants — enhancements already applied,
                    #    so we pass disable flags to avoid double-processing.
                    pre_resize_dims = getattr(self.camera_config, 'pre_resize_dimensions', [])
                    if pre_resize_dims:
                        pre_resize_dict = resize_and_compress_frame(
                            enhanced_frame,
                            sizes=pre_resize_dims,
                            format=_fmt,
                            quality=_quality,
                            enable_clahe=False,
                            enable_denoising=False,
                        )
                except ImportError as e:
                    self.logger.warning(f"preprocessing module not found, falling back to raw: {e}")
                except Exception as e:
                    self.logger.warning(f"Failed to compress frame, falling back to raw: {e}")
                    
            # Write the base full-res frame
            shared_memory_key = self.shared_memory.write_frame(frame, compressed_bytes=compressed_bytes)
            
            # Write pre-resized frames if successfully generated
            if pre_resize_dict:
                for size, cbytes in pre_resize_dict.items():
                    suffix_key = f"{shared_memory_key}_{size}"
                    try:
                        self.shared_memory.write_frame(frame, compressed_bytes=cbytes, custom_key=suffix_key)
                    except Exception as e:
                        self.logger.warning(f"Failed to write pre-resized frame {size}: {e}")
            
            # Generate frame ID
            frame_id = TaskMetadata.generate_frame_id(self.camera_config.camera_id)
            
            # Publish to worker queues based on camera priority configuration
            # Camera priority determines which queues to send to:
            # - "ALL": Send to all worker queues (critical, high, medium)
            # - Specific priority: Send to that priority queue only
            camera_priority = getattr(self.camera_config, 'priority', 'all').lower()
            
            if camera_priority == 'all' or camera_priority == '':
                # "ALL" priority: Send to all worker queues (weapon, fire, fall)
                target_queues = ["critical", "high", "medium"]
            elif camera_priority in ["critical", "high", "medium", "low"]:
                # Specific priority: Send to that queue only
                target_queues = [camera_priority]
            else:
                # Invalid priority: Default to all queues
                target_queues = ["critical", "high", "medium"]
            
            for priority in target_queues:
                task = TaskMetadata(
                    camera_id=self.camera_config.camera_id,
                    frame_id=frame_id,
                    shared_memory_key=shared_memory_key,
                    timestamp=time.time(),
                    priority=priority
                )
                self.redis_producer.enqueue(task)
            
            self.logger.debug(
                f"Frame processed and enqueued to all queues",
                extra={
                    "frame_id": frame_id,
                    "shared_memory_key": shared_memory_key
                }
            )
            
        except MemoryError as e:
            # Shared memory full - skip frame safely
            self.logger.warning(
                f"Shared memory full, skipping frame: {e}",
                extra={"error": str(e)}
            )
        except Exception as e:
            self.logger.error(
                f"Error processing frame: {e}",
                extra={"error": str(e)}
            )
    
    def _shutdown(self) -> None:
        """Cleanup resources."""
        self.logger.info("Shutting down camera process")
        
        # Disconnect RTSP
        if self.rtsp_handler:
            self.rtsp_handler.disconnect()
        
        # Disconnect Redis
        if self.redis_producer:
            self.redis_producer.disconnect()
        
        # NOTE: Do NOT cleanup shared frames here!
        # Workers may still need frame files for tasks already in the queue.
        # Frame files sit on tmpfs and are cleaned on container restart.
        # if self.shared_memory:
        #     self.shared_memory.cleanup_all()
        
        # Log final statistics
        if self.frame_grabber:
            self.logger.info(
                "Frame grabber stats",
                extra=self.frame_grabber.get_stats()
            )
        
        if self.motion_detector:
            self.logger.info(
                "Motion detector stats",
                extra=self.motion_detector.get_stats()
            )
        
        if self.redis_producer:
            self.logger.info(
                "Redis producer stats",
                extra=self.redis_producer.get_stats()
            )
        
        self.logger.info("Camera process shutdown complete")
