"""
VisionGuard AI - Redis Producer

Enqueues task metadata to Redis queues.
NO frames, only metadata references.
"""

import redis
import json
import logging
from typing import Optional, Deque
from collections import deque
from ..redis_queue.task_models import TaskMetadata, REDIS_QUEUES
from ..config import RedisConfig, BufferConfig
from ..utils.retry import RetryContext


class RedisProducer:
    """
    Redis task queue producer.
    
    Enqueues task metadata (NOT frames) to priority-based Redis queues.
    Handles Redis unavailability with brief buffering.
    """
    
    def __init__(
        self,
        redis_config: RedisConfig,
        buffer_config: BufferConfig,
        camera_id: str = "unknown"
    ):
        """
        Initialize Redis producer.
        
        Args:
            redis_config: Redis connection configuration
            buffer_config: Buffer configuration for unavailability
            camera_id: Camera identifier for logging
        """
        self.redis_config = redis_config
        self.buffer_config = buffer_config
        self.camera_id = camera_id
        self.logger = logging.getLogger(__name__)
        
        # Redis client
        self.client: Optional[redis.Redis] = None
        self.is_connected = False
        
        # Buffer for when Redis is unavailable
        self.buffer: Deque[TaskMetadata] = deque(maxlen=buffer_config.max_buffer_size)
        
        # Statistics
        self.tasks_enqueued = 0
        self.tasks_buffered = 0
        self.tasks_dropped = 0
        self.connection_failures = 0
    
    def connect(self) -> bool:
        """
        Connect to Redis with retry logic.
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.client = redis.Redis(
                host=self.redis_config.host,
                port=self.redis_config.port,
                db=self.redis_config.db,
                password=self.redis_config.password,
                socket_timeout=self.redis_config.socket_timeout,
                retry_on_timeout=self.redis_config.retry_on_timeout,
                decode_responses=True  # Get strings instead of bytes
            )
            
            # Test connection
            self.client.ping()
            
            self.is_connected = True
            self.logger.info(
                f"Connected to Redis",
                extra={
                    "host": self.redis_config.host,
                    "port": self.redis_config.port,
                    "db": self.redis_config.db
                }
            )
            
            # Flush buffer if we have pending tasks
            self._flush_buffer()
            
            return True
            
        except Exception as e:
            self.logger.error(
                f"Failed to connect to Redis: {e}",
                extra={"error": str(e)}
            )
            self.is_connected = False
            self.connection_failures += 1
            return False
    
    def enqueue(self, task: TaskMetadata) -> bool:
        """
        Enqueue task metadata to Redis.
        
        If Redis is unavailable, task is buffered briefly.
        If buffer is full, oldest/newest task is dropped based on policy.
        
        Args:
            task: Task metadata to enqueue
            
        Returns:
            True if enqueued successfully, False if buffered or dropped
        """
        # If not connected, try to reconnect
        if not self.is_connected:
            self.connect()
        
        # If still not connected, buffer the task
        if not self.is_connected:
            return self._buffer_task(task)
        
        try:
            # Get queue name based on priority
            queue_name = task.get_queue_name()
            
            # Serialize task
            task_json = json.dumps(task.to_dict())
            
            # Enqueue to Redis (LPUSH for queue)
            self.client.lpush(queue_name, task_json)
            
            self.tasks_enqueued += 1
            
            self.logger.debug(
                f"Enqueued task to Redis",
                extra={
                    "queue": queue_name,
                    "camera_id": task.camera_id,
                    "frame_id": task.frame_id,
                    "priority": task.priority
                }
            )
            
            return True
            
        except redis.RedisError as e:
            self.logger.warning(
                f"Redis error during enqueue: {e}",
                extra={"error": str(e)}
            )
            self.is_connected = False
            return self._buffer_task(task)
            
        except Exception as e:
            self.logger.error(
                f"Unexpected error during enqueue: {e}",
                extra={"error": str(e)}
            )
            return False
            
    def get_queue_length(self, queue_name: str) -> int:
        """
        Get the current length of the specified Redis queue.
        Used for backpressure monitoring.
        
        Args:
            queue_name: The name of the Redis list/queue.
            
        Returns:
            The integer length of the queue, or 0 if disconnected/error.
        """
        if not self.is_connected or not self.client:
            return 0
            
        try:
            return self.client.llen(queue_name)
        except redis.RedisError as e:
            self.logger.warning(
                f"Redis error checking queue length: {e}",
                extra={"error": str(e)}
            )
            self.is_connected = False
            return 0
    
    def _buffer_task(self, task: TaskMetadata) -> bool:
        """
        Buffer task when Redis is unavailable.
        
        Args:
            task: Task to buffer
            
        Returns:
            True if buffered, False if dropped
        """
        # Check if buffer is full
        if len(self.buffer) >= self.buffer_config.max_buffer_size:
            # Drop based on policy
            if self.buffer_config.drop_policy == "oldest":
                dropped = self.buffer.popleft()
                self.logger.warning(
                    f"Buffer full, dropped oldest task",
                    extra={"dropped_frame_id": dropped.frame_id}
                )
            else:  # newest
                self.logger.warning(
                    f"Buffer full, dropping newest task",
                    extra={"dropped_frame_id": task.frame_id}
                )
                self.tasks_dropped += 1
                return False
            
            self.tasks_dropped += 1
        
        # Add to buffer
        self.buffer.append(task)
        self.tasks_buffered += 1
        
        self.logger.debug(
            f"Buffered task (Redis unavailable)",
            extra={
                "buffer_size": len(self.buffer),
                "frame_id": task.frame_id
            }
        )
        
        return True
    
    def _flush_buffer(self) -> None:
        """Flush buffered tasks to Redis."""
        if not self.buffer:
            return
        
        self.logger.info(
            f"Flushing buffer to Redis",
            extra={"buffer_size": len(self.buffer)}
        )
        
        flushed = 0
        failed = 0
        
        while self.buffer:
            task = self.buffer.popleft()
            
            try:
                queue_name = task.get_queue_name()
                task_json = json.dumps(task.to_dict())
                self.client.lpush(queue_name, task_json)
                flushed += 1
                self.tasks_enqueued += 1
                
            except Exception as e:
                self.logger.error(
                    f"Failed to flush task: {e}",
                    extra={"frame_id": task.frame_id, "error": str(e)}
                )
                failed += 1
                # Put it back in buffer
                self.buffer.appendleft(task)
                break
        
        self.logger.info(
            f"Buffer flush complete",
            extra={"flushed": flushed, "failed": failed, "remaining": len(self.buffer)}
        )
    
    def get_stats(self) -> dict:
        """
        Get Redis producer statistics.
        
        Returns:
            Dictionary with connection status and task counts
        """
        return {
            "is_connected": self.is_connected,
            "tasks_enqueued": self.tasks_enqueued,
            "tasks_buffered": self.tasks_buffered,
            "tasks_dropped": self.tasks_dropped,
            "buffer_size": len(self.buffer),
            "connection_failures": self.connection_failures
        }
    
    def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            try:
                self.client.close()
            except:
                pass
            
            self.client = None
            self.is_connected = False
            
            self.logger.info("Disconnected from Redis")
    
    def __del__(self):
        """Cleanup on deletion."""
        self.disconnect()
