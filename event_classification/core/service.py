"""
VisionGuard AI - Event Classification Service

Single-instance, CPU-only, deterministic classification brain.
Sole authority for event classification, frame correlation, and shared memory cleanup.
"""

import logging
import os
import time
import redis as redis_lib
from multiprocessing import Process, Event as ProcessEvent
from typing import Optional

from ..config import ECSConfig
from ..buffer.frame_buffer import FrameBuffer
from ..buffer.frame_state import AIResult
from ..buffer.camera_history import CameraHistoryManager
from ..classification.rule_engine import RuleEngine
from ..redis_client.stream_consumer import StreamConsumer
from ..cleanup.cleanup_manager import CleanupManager
from ..output.alert_dispatcher import AlertDispatcher
from ..output.database_writer import DatabaseWriter
from ..output.frontend_publisher import FrontendPublisher


class ECSService:
    """
    Event Classification Service (ECS).
    
    Single-instance, deterministic classification brain.
    
    Main loop:
    1. Consume AI results from Redis stream
    2. Add to frame buffer
    3. Check if ready for classification (correlation window or weapon short-circuit)
    4. Apply deterministic classification rules
    5. Dispatch outputs (async, non-blocking)
    6. Cleanup shared memory (AUTHORITATIVE)
    7. Remove from buffer
    8. Handle expired frames (TTL-based)
    """
    
    def __init__(self, config: ECSConfig):
        """
        Initialize ECS.
        
        Args:
            config: ECS configuration
        """
        self.config = config
        
        # Process control
        self.process: Optional[Process] = None
        self.stop_event = ProcessEvent()
        
        # Components (initialized in process)
        self.logger: Optional[logging.Logger] = None
        self.frame_buffer: Optional[FrameBuffer] = None
        self.rule_engine: Optional[RuleEngine] = None
        self.stream_consumer: Optional[StreamConsumer] = None
        self.cleanup_manager: Optional[CleanupManager] = None
        self.alert_dispatcher: Optional[AlertDispatcher] = None
        self.database_writer: Optional[DatabaseWriter] = None
        self.frontend_publisher: Optional[FrontendPublisher] = None
        # V2: Camera history manager
        self.camera_history_manager: Optional[CameraHistoryManager] = None
        # Clip request publisher
        self._clip_redis: Optional[redis_lib.Redis] = None
    
    def start(self) -> bool:
        """
        Start ECS process.
        
        Returns:
            True if process started successfully
        """
        self.stop_event.clear()
        
        self.process = Process(
            target=self._run,
            name="ECS-Service",
            daemon=False
        )
        self.process.start()
        
        return self.process.is_alive()
    
    def stop(self, timeout: float = 10.0) -> None:
        """
        Stop ECS process gracefully.
        
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
        
        This is the entry point for the ECS process.
        """
        # Setup logging for this process
        self.logger = logging.getLogger("event_classification")
        self.logger.setLevel(getattr(logging, self.config.log_level))
        
        handler = logging.StreamHandler()
        if self.config.log_format == "json":
            # TODO: Use JSON formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        self.logger.info("ECS starting (SINGLE INSTANCE)")
        
        try:
            # Initialize components
            if not self._initialize():
                self.logger.error("Failed to initialize ECS")
                return
            
            # Main classification loop
            self._classification_loop()
            
        except Exception as e:
            self.logger.error(
                f"Fatal error in ECS: {e}",
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
            # Initialize frame buffer
            self.frame_buffer = FrameBuffer()
            
            # Initialize rule engine
            self.rule_engine = RuleEngine(self.config)
            
            # V2: Initialize camera history manager
            self.camera_history_manager = CameraHistoryManager(
                history_window_seconds=self.config.camera_history_window_sec
            )
            self.logger.info(
                "CameraHistoryManager initialized",
                extra={"window_sec": self.config.camera_history_window_sec}
            )
            
            # Initialize Redis stream consumer
            self.stream_consumer = StreamConsumer(
                stream_name=self.config.input_stream,
                redis_host=self.config.redis_host,
                redis_port=self.config.redis_port,
                redis_db=self.config.redis_db,
                redis_password=self.config.redis_password,
                block_ms=self.config.read_block_ms,
                count=self.config.read_count
            )
            
            # REFINEMENT: Set start ID based on config
            if self.config.resume_from_latest:
                self.stream_consumer.set_start_id("$")  # Start from latest
            else:
                # Read from beginning (explicit backlog replay)
                self.stream_consumer.set_start_id("0")  # Start from first message
            
            # Initialize cleanup manager (AUTHORITATIVE)
            self.cleanup_manager = CleanupManager()
            
            # Initialize output dispatchers
            if self.config.enable_alerts:
                self.alert_dispatcher = AlertDispatcher()
            
            if self.config.enable_database:
                self.database_writer = DatabaseWriter(
                    enabled=True,
                    db_path=self.config.database_path,
                    batch_size=self.config.database_batch_size,
                    model_version=self.config.model_version
                )
            
            if self.config.enable_frontend:
                self.frontend_publisher = FrontendPublisher()
            
            self.logger.info("ECS initialized successfully")

            # Connect clip Redis client (non-critical — failure doesn't block ECS)
            try:
                self._clip_redis = redis_lib.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    db=self.config.redis_db or 0,
                    decode_responses=True,
                )
                self._clip_redis.ping()
                self.logger.info("Clip Redis client connected")
            except Exception as e:
                self.logger.warning(f"Clip Redis client failed to connect: {e} — clip publishing disabled")
                self._clip_redis = None

            return True
            
        except Exception as e:
            self.logger.error(
                f"Initialization failed: {e}",
                extra={"error": str(e)}
            )
            return False
    
    def _classification_loop(self) -> None:
        """Main classification loop."""
        self.logger.info("Starting classification loop (v2)")

        last_heartbeat = time.time()
        heartbeat_interval_sec = 30.0
        last_classification_scan = time.time()
        
        while not self.stop_event.is_set():
            try:
                # 1. Consume messages from Redis stream
                messages = self.stream_consumer.consume()
                
                for msg in messages:
                    ingest_timestamp = time.time()
                    try:
                        ingest_timestamp = int(str(msg.id).split("-", 1)[0]) / 1000.0
                    except Exception:
                        pass

                    self.logger.debug(
                        "ECS raw Redis message",
                        extra={
                            "camera_id": msg.camera_id,
                            "model_type": msg.model_type,
                            "confidence": msg.confidence,
                            "frame_id": msg.frame_id
                        }
                    )
                    
                    # 2. Add result to frame buffer
                    ai_result = AIResult(
                        model_type=msg.model_type,
                        confidence=msg.confidence,
                        timestamp=msg.timestamp,
                        ingest_timestamp=ingest_timestamp,
                        bbox=msg.bbox
                    )
                    
                    frame_state = self.frame_buffer.add_result(
                        frame_id=msg.frame_id,
                        camera_id=msg.camera_id,
                        shared_memory_key=msg.shared_memory_key,
                        model_type=msg.model_type,
                        result=ai_result
                    )
                    
                    # 3. Check if ready for classification
                    # Weapon short-circuits correlation window
                    should_classify = False
                    
                    if self.rule_engine.should_classify_immediately(frame_state):
                        should_classify = True
                        self.logger.debug(
                            f"Weapon detected - immediate classification",
                            extra={"frame_id": msg.frame_id}
                        )
                    elif frame_state.get_age_ms() >= self.config.correlation_window_ms:
                        should_classify = True
                        self.logger.debug(
                            f"Correlation window elapsed - classifying",
                            extra={
                                "frame_id": msg.frame_id,
                                "age_ms": frame_state.get_age_ms()
                            }
                        )
                    
                    if should_classify:
                        # 4. Classify with camera history (v2)
                        camera_history = self.camera_history_manager.get(
                            frame_state.camera_id
                        )
                        frame_state.classification_attempted = True
                        event = self.rule_engine.classify(
                            frame_state, camera_history
                        )
                        
                        if event:
                            # 5. Dispatch outputs
                            if self.alert_dispatcher:
                                self.alert_dispatcher.dispatch(event)
                            if self.database_writer:
                                self.database_writer.write(event)
                            if self.frontend_publisher:
                                self.frontend_publisher.publish(event)
                            self._publish_clip_request(event)
                        
                        # 6. Cleanup shared memory
                        self.cleanup_manager.cleanup_frame(
                            frame_state.shared_memory_key
                        )
                        # 7. Remove from buffer
                        self.frame_buffer.remove_frame(msg.frame_id)
                
                # 8. V2 Periodic classification scan
                current_time = time.time()
                if current_time - last_classification_scan >= 1.0:
                    aged_frames = (
                        self.frame_buffer.get_frames_needing_classification(
                            self.config.correlation_window_ms
                        )
                    )
                    
                    for frame_state in aged_frames:
                        frame_state.classification_attempted = True
                        camera_history = self.camera_history_manager.get(
                            frame_state.camera_id
                        )
                        event = self.rule_engine.classify(
                            frame_state, camera_history
                        )
                        
                        if event:
                            self.logger.info(
                                f"Classified aged frame: {event.event_type}",
                                extra={
                                    "frame_id": frame_state.frame_id,
                                    "event_type": event.event_type,
                                    "confidence": event.confidence,
                                    "age_ms": frame_state.get_age_ms()
                                }
                            )
                            if self.alert_dispatcher:
                                self.alert_dispatcher.dispatch(event)
                            if self.database_writer:
                                self.database_writer.write(event)
                            if self.frontend_publisher:
                                self.frontend_publisher.publish(event)
                            self._publish_clip_request(event)
                        
                        self.cleanup_manager.cleanup_frame(
                            frame_state.shared_memory_key
                        )
                        self.frame_buffer.remove_frame(
                            frame_state.frame_id
                        )
                    
                    last_classification_scan = current_time
                
                # 9. Handle expired frames (safety net)
                expired_frames = self.frame_buffer.get_expired_frames(
                    self.config.hard_ttl_seconds
                )
                
                for frame_state in expired_frames:
                    # Force classify before expiry
                    if not frame_state.classification_attempted:
                        frame_state.classification_attempted = True
                        frame_state.classification_reason = "ttl_expiry"
                        camera_history = self.camera_history_manager.get(
                            frame_state.camera_id
                        )
                        event = self.rule_engine.classify(
                            frame_state, camera_history
                        )
                        if event:
                            self.logger.info(
                                f"TTL expiry classification: {event.event_type}",
                                extra={
                                    "frame_id": frame_state.frame_id,
                                    "event_type": event.event_type,
                                    "confidence": event.confidence,
                                }
                            )
                            if self.alert_dispatcher:
                                self.alert_dispatcher.dispatch(event)
                            if self.database_writer:
                                self.database_writer.write(event)
                            if self.frontend_publisher:
                                self.frontend_publisher.publish(event)
                            self._publish_clip_request(event)
                    
                    self.logger.warning(
                        f"Frame expired (TTL)",
                        extra={
                            "frame_id": frame_state.frame_id,
                            "age_ms": frame_state.get_age_ms()
                        }
                    )
                    self.cleanup_manager.cleanup_frame(
                        frame_state.shared_memory_key
                    )
                    self.frame_buffer.remove_frame(frame_state.frame_id)

                if time.time() - last_heartbeat >= heartbeat_interval_sec:
                    self.logger.info(
                        "ECS v2 heartbeat",
                        extra={
                            "buffer_size": self.frame_buffer.get_buffer_size(),
                            "messages_consumed": self.stream_consumer.messages_consumed,
                            "cameras_tracked": self.camera_history_manager.camera_count(),
                            "rule_engine_stats": self.rule_engine.get_stats()
                        }
                    )
                    last_heartbeat = time.time()
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(
                    f"Error in classification loop: {e}",
                    extra={"error": str(e)}
                )
                # Continue processing
                time.sleep(0.1)
        
        self.logger.info("Classification loop ended")
    
    def _shutdown(self) -> None:
        """Cleanup resources."""
        self.logger.info("Shutting down ECS")
        
        # Close Redis connection
        if self.stream_consumer:
            self.stream_consumer.close()
        
        # Log final statistics
        if self.frame_buffer:
            self.logger.info(
                "Frame buffer stats",
                extra=self.frame_buffer.get_stats()
            )
        
        if self.rule_engine:
            self.logger.info(
                "Rule engine stats",
                extra=self.rule_engine.get_stats()
            )
        
        if self.stream_consumer:
            self.logger.info(
                "Stream consumer stats",
                extra=self.stream_consumer.get_stats()
            )
        
        if self.cleanup_manager:
            self.logger.info(
                "Cleanup manager stats",
                extra=self.cleanup_manager.get_stats()
            )
        
        if self.alert_dispatcher:
            self.logger.info(
                "Alert dispatcher stats",
                extra=self.alert_dispatcher.get_stats()
            )
        
        if self.database_writer:
            self.logger.info(
                "Database writer stats",
                extra=self.database_writer.get_stats()
            )
        
        if self.frontend_publisher:
            self.logger.info(
                "Frontend publisher stats",
                extra=self.frontend_publisher.get_stats()
            )
        
        self.logger.info("ECS shutdown complete")

    def _publish_clip_request(self, event) -> None:
        """
        Publish a clip recording request to the vg:clip:requests Redis stream.

        Non-blocking — any failure is logged as a warning and never raised.
        Only called inside `if event:` blocks, so event is always valid.

        Args:
            event: Classified Event object
        """
        if self._clip_redis is None:
            return
        try:
            import time as _time
            # Look up the camera source URL from the registry the camera service populates.
            # This means cameras.json is the SINGLE source of truth — no env var needed.
            camera_source = ""
            try:
                camera_source = self._clip_redis.hget("vg:camera:sources", event.camera_id) or ""
            except Exception:
                pass

            self._clip_redis.xadd(
                "vg:clip:requests",
                {
                    "event_id":      str(event.event_id),
                    "event_type":    str(event.event_type),
                    "camera_id":     str(event.camera_id),
                    "camera_source": camera_source,
                    "timestamp":     str(event.timestamp),
                    "confidence":    str(event.confidence),
                },
                maxlen=500,  # Cap stream to avoid unbounded growth
                approximate=True,
            )
            self.logger.debug(
                f"Clip request published for event {event.event_id}",
                extra={"event_type": event.event_type, "camera_id": event.camera_id},
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to publish clip request for event {event.event_id}: {e}"
            )
