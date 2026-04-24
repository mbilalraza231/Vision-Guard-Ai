"""
VisionGuard AI - AI Worker Process

Main worker process for single-model inference.
Consumes from ONE queue, runs ONE model, publishes to results stream.
"""

import time
import logging
import os
import cv2
from multiprocessing import Process, Event
from typing import Optional

from ..config import WorkerConfig
from ..utils.logging import setup_worker_logging
from ..redis_client.task_consumer import TaskConsumer
from ..redis_client.result_publisher import ResultPublisher
from ..shared_memory.frame_manager import FrameManager
from ..inference.model_loader import ModelLoader
from ..inference.preprocessor import Preprocessor
from ..inference.inference_engine import InferenceEngine
from ..inference.postprocessor import Postprocessor


class AIWorker:
    """
    Single-model AI inference worker.
    
    Main loop:
    1. Consume task from Redis queue
    2. Read frame from shared memory (READ-ONLY)
    3. Preprocess frame
    4. Run ONNX inference
    5. Postprocess result
    6. Publish result to Redis stream (with shared_memory_key)
    
    NO cleanup - Event Classification Service owns frame lifecycle.
    """
    
    def __init__(self, config: WorkerConfig):
        """
        Initialize AI worker.
        
        Args:
            config: Worker configuration
        """
        self.config = config
        
        # Process control
        self.process: Optional[Process] = None
        self.stop_event = Event()
        
        # Components (initialized in process)
        self.logger: Optional[logging.Logger] = None
        self.task_consumer: Optional[TaskConsumer] = None
        self.result_publisher: Optional[ResultPublisher] = None
        self.frame_manager: Optional[FrameManager] = None
        self.model_loader: Optional[ModelLoader] = None
        self.preprocessor: Optional[Preprocessor] = None
        self.inference_engine: Optional[InferenceEngine] = None
        self.postprocessor: Optional[Postprocessor] = None
    
    def start(self) -> bool:
        """
        Start worker process.
        
        Returns:
            True if process started successfully
        """
        self.stop_event.clear()
        
        self.process = Process(
            target=self._run,
            name=f"AIWorker-{self.config.model_type}",
            daemon=False
        )
        self.process.start()
        
        return self.process.is_alive()
    
    def stop(self, timeout: float = 10.0) -> None:
        """
        Stop worker process gracefully.
        
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
        
        This is the entry point for the worker process.
        """
        # Setup logging for this process
        self.logger = setup_worker_logging(
            model_type=self.config.model_type,
            level=self.config.log_level,
            format_type=self.config.log_format
        )
        
        self.logger.info(
            f"AI Worker starting",
            extra={
                "model_type": self.config.model_type,
                "queue": self.config.redis_input_queue,
                "model_path": self.config.onnx_model_path
            }
        )
        
        try:
            # Initialize components
            if not self._initialize():
                self.logger.error("Failed to initialize AI worker")
                return
            
            # Main inference loop
            self._inference_loop()
            
        except Exception as e:
            self.logger.error(
                f"Fatal error in AI worker: {e}",
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
            # Initialize Redis task consumer
            self.task_consumer = TaskConsumer(
                queue_name=self.config.redis_input_queue,
                redis_host=self.config.redis_host,
                redis_port=self.config.redis_port,
                redis_db=self.config.redis_db,
                redis_password=self.config.redis_password,
                timeout=self.config.redis_timeout
            )
            
            # Initialize Redis result publisher
            self.result_publisher = ResultPublisher(
                redis_host=self.config.redis_host,
                redis_port=self.config.redis_port,
                redis_db=self.config.redis_db,
                redis_password=self.config.redis_password
            )
            
            # Initialize frame manager (READ-ONLY)
            self.frame_manager = FrameManager(
                max_frame_size_mb=self.config.shared_memory_max_size_mb
            )
            
            # Load model (auto-detects ONNX file vs OpenVINO directory)
            self.model_loader = ModelLoader(
                model_path=self.config.onnx_model_path,
                intra_op_num_threads=self.config.intra_op_num_threads,
                inter_op_num_threads=self.config.inter_op_num_threads
            )
            
            # Initialize preprocessor
            self.preprocessor = Preprocessor(
                target_size=(self.config.input_width, self.config.input_height)
            )
            
            # Use the engine returned by ModelLoader (OpenVINO or ONNX)
            self.inference_engine = self.model_loader.get_engine()
            
            # Initialize postprocessor with tuned NMS parameters
            self.postprocessor = Postprocessor(
                confidence_threshold=self.config.confidence_threshold,
                iou_threshold=self.config.iou_threshold,
                agnostic_nms=self.config.agnostic_nms,
                allowed_class_ids=self.config.allowed_class_ids
            )
            
            self.logger.info("AI Worker initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(
                f"Initialization failed: {e}",
                extra={"error": str(e)}
            )
            return False
    
    def _inference_loop(self) -> None:
        """Main inference loop."""
        self.logger.info("Starting inference loop")
        
        # Store base logger to avoid recursive LoggerAdapter wrapping
        base_logger = self.logger

        last_heartbeat = time.time()
        heartbeat_interval_sec = 30.0
        
        while not self.stop_event.is_set():
            try:
                # 1. Consume task from Redis queue
                task = self.task_consumer.consume()
                
                if task is None:
                    # Timeout - no task available
                    continue
                
                # Create fresh adapter from BASE logger (not self.logger!)
                # Previous code wrapped self.logger repeatedly, causing
                # RecursionError after ~800 frames
                self.logger = logging.LoggerAdapter(
                    base_logger,
                    {
                        'camera_id': task.camera_id,
                        'frame_id': task.frame_id
                    }
                )
                
                # Track inference timing
                start_time = time.time()
                
                # Log task consumption
                base_logger.info(
                    f"Processing task {task.frame_id}",
                    extra={
                        "camera_id": task.camera_id,
                        "model": self.config.model_type,
                        "shared_memory_key": task.shared_memory_key
                    }
                )
                
                # 2. Read frame from shared memory (READ-ONLY)
                frame = self.frame_manager.read_frame(task.shared_memory_key)
                
                if frame is None:
                    base_logger.error(
                        f"FRAME_NOT_FOUND {task.frame_id}",
                        extra={
                            "camera_id": task.camera_id,
                            "shared_memory_key": task.shared_memory_key
                        }
                    )
                    continue
                
                # 3. Preprocess
                input_tensor = self.preprocessor.preprocess(frame)
                
                # 4. Run inference
                output = self.inference_engine.run(input_tensor)
                
                # 5. Postprocess
                result = self.postprocessor.postprocess(output)
                
                # 6. Calculate inference latency
                inference_latency_ms = (time.time() - start_time) * 1000
                
                # 7. Publish result (if confidence met)
                if result:
                    result["inference_latency_ms"] = inference_latency_ms
                    
                    # Save detection image with bounding box (only if above image threshold)
                    # Image threshold is higher than publish threshold to reduce gallery noise
                    image_threshold = float(os.getenv("IMAGE_SAVE_THRESHOLD", "0.50"))
                    detection_image_path = ""
                    if result.get("confidence", 0) >= image_threshold:
                        detection_image_path = self._save_detection_image(
                            frame, result, task, base_logger
                        )
                        if detection_image_path:
                            result["detection_image"] = detection_image_path
                    
                    self.result_publisher.publish(
                        task=task,
                        result=result,
                        model_type=self.config.model_type
                    )
                    
                    base_logger.info(
                        f"DETECTION {task.frame_id} confidence={result.get('confidence', 0):.3f}",
                        extra={
                            "camera_id": task.camera_id,
                            "model": self.config.model_type,
                            "confidence": result.get("confidence"),
                            "inference_latency_ms": round(inference_latency_ms, 2),
                            "detection_image": detection_image_path or "none"
                        }
                    )
                else:
                    base_logger.debug(
                        f"BELOW_THRESHOLD {task.frame_id}",
                        extra={
                            "camera_id": task.camera_id,
                            "model": self.config.model_type,
                            "inference_latency_ms": round(inference_latency_ms, 2)
                        }
                    )
                
                # NO CLEANUP - AI Worker is READ-ONLY
                # Event Classification Service owns frame cleanup

                if time.time() - last_heartbeat >= heartbeat_interval_sec:
                    base_logger.info(
                        "AI worker heartbeat",
                        extra={
                            "tasks_consumed": self.task_consumer.tasks_consumed,
                            "publish_failures": self.result_publisher.publish_failures
                        }
                    )
                    last_heartbeat = time.time()
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(
                    f"Error in inference loop: {e}",
                    extra={"error": str(e)}
                )
                # Continue processing next task
                time.sleep(0.1)
        
        self.logger.info("Inference loop ended")
    
    def _save_detection_image(
        self,
        frame: 'np.ndarray',
        result: dict,
        task: 'TaskMetadata',
        logger: logging.Logger
    ) -> str:
        """
        Draw bounding box on frame and save as JPEG for debug UI.
        
        Returns the saved image path, or empty string on failure.
        """
        try:
            DETECTION_DIR = "/data/visionguard/detections"
            os.makedirs(DETECTION_DIR, exist_ok=True)
            
            # Make a copy to avoid modifying the original
            annotated = frame.copy()
            h, w = annotated.shape[:2]
            
            # Get bbox (in 640x640 preprocessed coords) and scale to original frame
            bbox = result.get("bbox")
            confidence = result.get("confidence", 0.0)
            
            if bbox and len(bbox) == 4:
                x1 = int(bbox[0] * w / 640)
                y1 = int(bbox[1] * h / 640)
                x2 = int(bbox[2] * w / 640)
                y2 = int(bbox[3] * h / 640)
                
                # Clamp to frame bounds
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                
                # Color by model type
                colors = {
                    "weapon": (0, 0, 255),    # Red
                    "fire":   (0, 140, 255),   # Orange
                    "fall":   (255, 100, 0),   # Blue
                }
                color = colors.get(self.config.model_type, (0, 255, 0))
                
                # Draw bounding box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
                
                # Draw label with confidence
                label = f"{self.config.model_type.upper()} {confidence:.2f}"
                font_scale = 0.8
                thickness = 2
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)
                cv2.putText(annotated, label, (x1, y1 - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness)
            
            # Save with timestamp-based filename
            ts = int(time.time() * 1000)
            filename = f"{self.config.model_type}_{task.camera_id}_{ts}.jpg"
            filepath = os.path.join(DETECTION_DIR, filename)
            cv2.imwrite(filepath, annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            
            # Auto-cleanup: keep only last 50 images per model type
            try:
                prefix = f"{self.config.model_type}_"
                all_images = sorted([
                    f for f in os.listdir(DETECTION_DIR)
                    if f.startswith(prefix) and f.endswith('.jpg')
                ])
                if len(all_images) > 50:
                    for old in all_images[:-50]:
                        os.remove(os.path.join(DETECTION_DIR, old))
            except Exception:
                pass
            
            return filepath
            
        except Exception as e:
            logger.warning(f"Failed to save detection image: {e}")
            return ""

    def _shutdown(self) -> None:
        """Cleanup resources."""
        self.logger.info("Shutting down AI worker")
        
        # Close Redis connections
        if self.task_consumer:
            self.task_consumer.close()
        
        if self.result_publisher:
            self.result_publisher.close()
        
        # Log final statistics
        if self.task_consumer:
            self.logger.info(
                "Task consumer stats",
                extra=self.task_consumer.get_stats()
            )
        
        if self.result_publisher:
            self.logger.info(
                "Result publisher stats",
                extra=self.result_publisher.get_stats()
            )
        
        if self.frame_manager:
            self.logger.info(
                "Frame manager stats",
                extra=self.frame_manager.get_stats()
            )
        
        if self.inference_engine:
            self.logger.info(
                "Inference engine stats",
                extra=self.inference_engine.get_stats()
            )
        
        self.logger.info("AI worker shutdown complete")
