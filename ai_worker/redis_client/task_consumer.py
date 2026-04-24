"""
VisionGuard AI - Redis Task Consumer

Consumes tasks from ONE dedicated Redis queue.
Worker is specialized for a single queue - no routing, no queue switching.
"""

import redis
import json
import logging
from typing import Optional
from dataclasses import dataclass


@dataclass
class TaskMetadata:
    """
    Task metadata from camera module.
    
    This is consumed from Redis queue (vg:critical, vg:high, or vg:medium).
    """
    camera_id: str
    frame_id: str
    shared_memory_key: str
    timestamp: float
    priority: str
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TaskMetadata':
        """Create from dictionary (Redis deserialization)."""
        return cls(
            camera_id=data["camera_id"],
            frame_id=data["frame_id"],
            shared_memory_key=data["shared_memory_key"],
            timestamp=data["timestamp"],
            priority=data["priority"]
        )


class TaskConsumer:
    """
    Redis task queue consumer.
    
    Consumes from ONE dedicated queue using BRPOP (blocking pop).
    Future-safe: Interface abstraction allows migration to Redis Streams consumer groups.
    """
    
    def __init__(
        self,
        queue_name: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        timeout: int = 1
    ):
        """
        Initialize task consumer.
        
        Args:
            queue_name: Redis queue to consume from (e.g., "vg:critical")
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database number
            redis_password: Redis password (optional)
            timeout: Blocking timeout in seconds
        """
        self.queue_name = queue_name
        self.timeout = timeout
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
        self.tasks_consumed = 0
        self.connection_errors = 0
        
        # Test connection
        try:
            self.client.ping()
            self.logger.info(
                f"Connected to Redis",
                extra={
                    "queue_name": queue_name,
                    "host": redis_host,
                    "port": redis_port
                }
            )
        except Exception as e:
            self.logger.error(
                f"Failed to connect to Redis: {e}",
                extra={"error": str(e)}
            )
            raise
    
    def consume(self, timeout: Optional[int] = None) -> Optional[TaskMetadata]:
        """
        Consume one task from the queue (blocking).
        
        Uses BRPOP (blocking right pop) for efficient queue consumption.
        
        Args:
            timeout: Override default timeout (seconds)
            
        Returns:
            TaskMetadata if task available, None if timeout
        """
        try:
            # BRPOP: blocks until task available or timeout
            result = self.client.brpop(
                self.queue_name,
                timeout=timeout or self.timeout
            )
            
            if result is None:
                # Timeout - no task available
                return None
            
            # Parse result: (queue_name, task_json)
            _, task_json = result
            
            # Deserialize task
            task_dict = json.loads(task_json)
            task = TaskMetadata.from_dict(task_dict)
            
            self.tasks_consumed += 1
            
            self.logger.debug(
                f"Consumed task from queue",
                extra={
                    "queue_name": self.queue_name,
                    "camera_id": task.camera_id,
                    "frame_id": task.frame_id,
                    "shared_memory_key": task.shared_memory_key
                }
            )
            
            return task
            
        except redis.RedisError as e:
            self.logger.error(
                f"Redis error during consume: {e}",
                extra={"queue_name": self.queue_name, "error": str(e)}
            )
            self.connection_errors += 1
            return None
            
        except json.JSONDecodeError as e:
            self.logger.error(
                f"Failed to decode task JSON: {e}",
                extra={"error": str(e)}
            )
            return None
            
        except Exception as e:
            self.logger.error(
                f"Unexpected error during consume: {e}",
                extra={"error": str(e)}
            )
            return None
    
    def get_stats(self) -> dict:
        """
        Get consumer statistics.
        
        Returns:
            Dictionary with tasks_consumed, connection_errors
        """
        return {
            "queue_name": self.queue_name,
            "tasks_consumed": self.tasks_consumed,
            "connection_errors": self.connection_errors
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
