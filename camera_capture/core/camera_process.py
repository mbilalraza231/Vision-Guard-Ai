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
                    # Stream likely dropped mid-run. Mark disconnected and let
                    # reconnect branch above handle recovery attempts.
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

                if time.time() - last_heartbeat >= heartbeat_interval_sec:
                    self.logger.info(
                        "Camera heartbeat",
                        extra={
                            "frames_processed": frames_processed,
                            "consecutive_read_failures": consecutive_read_failures,
                            "reconnect_attempts": reconnect_attempts,
                            "is_connected": self.rtsp_handler.is_connected if self.rtsp_handler else False,
                        }
                    )
                    last_heartbeat = time.time()
                
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
            # Write frame to shared memory
            shared_memory_key = self.shared_memory.write_frame(frame)
            
            # Generate frame ID
            frame_id = TaskMetadata.generate_frame_id(self.camera_config.camera_id)
            
            # Publish to ALL queues so each worker model gets the frame
            for priority in ["critical", "high", "medium"]:
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
