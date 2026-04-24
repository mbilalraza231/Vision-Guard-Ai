"""
VisionGuard AI - Redis Stream Consumer

Consumes AI results from vg:ai:results stream using XREAD.
Single reader, ordered processing, NO consumer groups.
"""

import redis
import json
import logging
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class StreamMessage:
    """
    Message from Redis stream.
    
    Parsed from vg:ai:results stream.
    """
    id: str  # Redis message ID
    frame_id: str
    camera_id: str
    model_type: str  # "weapon", "fire", "fall"
    confidence: float
    timestamp: float
    shared_memory_key: str
    bbox: Optional[list] = None  # [x1, y1, x2, y2]
    inference_latency_ms: Optional[float] = None
    
    @classmethod
    def from_redis_data(cls, msg_id: str, data: dict) -> 'StreamMessage':
        """
        Create from Redis stream data.
        
        Args:
            msg_id: Redis message ID
            data: Message data dictionary
            
        Returns:
            StreamMessage instance
        """
        # Parse bbox if present
        bbox = None
        if "bbox" in data and data["bbox"]:
            try:
                bbox = json.loads(data["bbox"]) if isinstance(data["bbox"], str) else data["bbox"]
            except:
                pass
        
        return cls(
            id=msg_id,
            frame_id=data["frame_id"],
            camera_id=data["camera_id"],
            # Worker sends "model", but we also accept "model_type" for compatibility
            model_type=data.get("model_type", data.get("model", "unknown")),
            confidence=float(data["confidence"]),
            timestamp=float(data["timestamp"]),
            shared_memory_key=data.get("shared_memory_key", ""),  # Optional field
            bbox=bbox,
            inference_latency_ms=float(data.get("inference_latency_ms", 0))
        )


class StreamConsumer:
    """
    Redis stream consumer for AI results.
    
    Consumes from vg:ai:results using XREAD (NOT consumer groups).
    Single reader, ordered processing.
    
    REFINEMENT: Tracks last_stream_id for crash recovery.
    """
    
    def __init__(
        self,
        stream_name: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        block_ms: int = 1000,
        count: int = 100
    ):
        """
        Initialize stream consumer.
        
        Args:
            stream_name: Redis stream name (vg:ai:results)
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database number
            redis_password: Redis password (optional)
            block_ms: XREAD block timeout in milliseconds
            count: Max messages to read per XREAD call
        """
        self.stream_name = stream_name
        self.block_ms = block_ms
        self.count = count
        self.logger = logging.getLogger(__name__)
        
        # REFINEMENT: Track last processed stream ID for crash recovery
        self.last_stream_id: str = "$"  # Start from latest by default
        
        # Redis client
        self.client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_keepalive=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Statistics
        self.messages_consumed = 0
        self.connection_errors = 0
        self.reconnection_attempts = 0
        
        # Validate connection on startup
        self._validate_connection()
    
    def _validate_connection(self) -> None:
        """Validate Redis connection on startup."""
        try:
            self.client.ping()
            self.logger.info(
                f"Connected to Redis stream",
                extra={
                    "stream": self.stream_name,
                    "host": self.client.connection_pool.connection_kwargs.get('host'),
                    "port": self.client.connection_pool.connection_kwargs.get('port')
                }
            )
        except redis.ConnectionError as e:
            self.logger.error(
                f"Failed to connect to Redis: {e}",
                extra={"error": str(e)}
            )
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error validating Redis connection: {e}",
                extra={"error": str(e)}
            )
            raise
    
    def _ensure_connection(self) -> bool:
        """
        Ensure Redis connection is alive, reconnect if needed.
        
        Returns:
            True if connection is valid, False otherwise
        """
        try:
            self.client.ping()
            return True
        except redis.ConnectionError:
            self.logger.warning("Redis connection lost, attempting reconnect...")
            self.reconnection_attempts += 1
            
            try:
                # Force close existing connection
                self.client.close()
                
                # Create new connection
                self.client.connection_pool.reset()
                self.client.ping()
                
                self.logger.info("Redis reconnection successful")
                return True
            except Exception as e:
                self.logger.error(
                    f"Redis reconnection failed: {e}",
                    extra={"error": str(e), "attempts": self.reconnection_attempts}
                )
                return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error checking Redis connection: {e}",
                extra={"error": str(e)}
            )
            return False
    
    def set_start_id(self, start_id: str) -> None:
        """
        Set starting stream ID for consumption.
        
        REFINEMENT: Allows resuming from last processed ID on restart.
        
        Args:
            start_id: Stream ID to start from ("$" for latest, "0" for beginning)
        """
        self.last_stream_id = start_id
        self.logger.info(
            f"Set stream start ID",
            extra={"start_id": start_id}
        )
    
    def consume(self) -> List[StreamMessage]:
        """
        Consume messages from stream using XREAD.
        
        Single reader, ordered processing.
        Blocks until messages available or timeout.
        
        Returns:
            List of StreamMessage objects
        """
        # Ensure connection is alive before attempting to read
        if not self._ensure_connection():
            self.logger.error("Cannot consume: Redis connection unavailable")
            self.connection_errors += 1
            return []
        
        try:
            # XREAD BLOCK <block_ms> COUNT <count> STREAMS <stream_name> <last_id>
            result = self.client.xread(
                {self.stream_name: self.last_stream_id},
                block=self.block_ms,
                count=self.count
            )
            
            if not result:
                # Timeout - no messages
                return []
            
            messages = []
            
            # Parse result: [(stream_name, [(msg_id, data), ...])]
            for stream, msgs in result:
                for msg_id, data in msgs:
                    try:
                        message = StreamMessage.from_redis_data(msg_id, data)
                        messages.append(message)
                        
                        # REFINEMENT: Update last processed ID for crash recovery
                        self.last_stream_id = msg_id
                        self.messages_consumed += 1
                        
                        self.logger.debug(
                            f"Consumed message from stream",
                            extra={
                                "message_id": msg_id,
                                "frame_id": message.frame_id,
                                "camera_id": message.camera_id,
                                "model_type": message.model_type
                            }
                        )
                        
                    except Exception as e:
                        self.logger.error(
                            f"Failed to parse stream message: {e}",
                            extra={"message_id": msg_id, "error": str(e)}
                        )
                        # Continue processing other messages
                        continue
            
            return messages
            
        except redis.RedisError as e:
            self.logger.error(
                f"Redis error during stream read: {e}",
                extra={"stream": self.stream_name, "error": str(e)}
            )
            self.connection_errors += 1
            return []
            
        except Exception as e:
            self.logger.error(
                f"Unexpected error during stream read: {e}",
                extra={"error": str(e)}
            )
            return []
    
    def get_last_id(self) -> str:
        """
        Get last processed stream ID.
        
        REFINEMENT: For crash recovery persistence.
        
        Returns:
            Last processed stream ID
        """
        return self.last_stream_id
    
    def get_stats(self) -> dict:
        """
        Get consumer statistics.
        
        Returns:
            Dictionary with consumer stats
        """
        return {
            "stream": self.stream_name,
            "messages_consumed": self.messages_consumed,
            "connection_errors": self.connection_errors,
            "reconnection_attempts": self.reconnection_attempts,
            "last_stream_id": self.last_stream_id
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
