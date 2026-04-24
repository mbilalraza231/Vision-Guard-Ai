"""
VisionGuard AI - Redis Result Publisher

Publishes inference results to Redis stream.
Results include shared_memory_key for Event Classification Service cleanup.
"""

import redis
import json
import logging
import time
from typing import Optional
from ..config import ResultMetadata
from ..redis_client.task_consumer import TaskMetadata


class ResultPublisher:
    """
    Redis stream publisher for inference results.
    
    Publishes to 'vg:ai:results' stream.
    Retry briefly on failure, then drop (no blocking).
    """
    
    RESULT_STREAM = "vg:ai:results"
    MAX_RETRIES = 3
    RETRY_DELAY = 0.1  # seconds
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None
    ):
        """
        Initialize result publisher.
        
        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database number
            redis_password: Redis password (optional)
        """
        self.logger = logging.getLogger(__name__)
        
        # Redis client
        self.client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_keepalive=True,
            socket_connect_timeout=5
        )
        
        # Statistics
        self.results_published = 0
        self.publish_failures = 0
        
        # Test connection
        try:
            self.client.ping()
            self.logger.info(
                f"Connected to Redis for result publishing",
                extra={"stream": self.RESULT_STREAM}
            )
        except Exception as e:
            self.logger.error(
                f"Failed to connect to Redis: {e}",
                extra={"error": str(e)}
            )
            raise
    
    def publish(
        self,
        task: TaskMetadata,
        result: dict,
        model_type: str
    ) -> bool:
        """
        Publish inference result to Redis stream.
        
        CRITICAL: Result includes shared_memory_key for Event Classification cleanup.
        
        Args:
            task: Original task metadata
            result: Inference result (confidence, bbox, etc.)
            model_type: Model type (weapon, fire, fall)
            
        Returns:
            True if published successfully, False otherwise
        """
        # Construct result metadata
        result_metadata = ResultMetadata(
            camera_id=task.camera_id,
            frame_id=task.frame_id,
            shared_memory_key=task.shared_memory_key,  # CRITICAL for cleanup
            model=model_type,
            confidence=result.get("confidence", 0.0),
            bbox=result.get("bbox"),
            timestamp=task.timestamp,
            inference_latency_ms=result.get("inference_latency_ms", 0.0),
            detection_image=result.get("detection_image")
        )
        
        # Convert to dict
        result_dict = result_metadata.to_dict()
        
        # Retry logic
        for attempt in range(self.MAX_RETRIES):
            try:
                # Publish to Redis stream (XADD)
                message_id = self.client.xadd(
                    self.RESULT_STREAM,
                    result_dict
                )
                
                self.results_published += 1
                
                self.logger.debug(
                    f"Published result to stream",
                    extra={
                        "stream": self.RESULT_STREAM,
                        "message_id": message_id,
                        "camera_id": task.camera_id,
                        "frame_id": task.frame_id,
                        "model": model_type,
                        "confidence": result.get("confidence"),
                        "inference_latency_ms": result.get("inference_latency_ms")
                    }
                )
                
                return True
                
            except redis.RedisError as e:
                self.logger.warning(
                    f"Redis error during publish (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "frame_id": task.frame_id
                    }
                )
                
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
                else:
                    # Max retries exceeded - drop result
                    self.publish_failures += 1
                    self.logger.error(
                        f"Failed to publish result after {self.MAX_RETRIES} attempts, dropping",
                        extra={"frame_id": task.frame_id}
                    )
                    return False
                    
            except Exception as e:
                self.logger.error(
                    f"Unexpected error during publish: {e}",
                    extra={"error": str(e), "frame_id": task.frame_id}
                )
                self.publish_failures += 1
                return False
        
        return False
    
    def get_stats(self) -> dict:
        """
        Get publisher statistics.
        
        Returns:
            Dictionary with results_published, publish_failures
        """
        return {
            "stream": self.RESULT_STREAM,
            "results_published": self.results_published,
            "publish_failures": self.publish_failures
        }
    
    def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            try:
                self.client.close()
                self.logger.info("Closed Redis connection")
            except:
                pass
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()
