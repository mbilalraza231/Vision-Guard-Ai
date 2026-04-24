"""
VisionGuard AI - Task Metadata Models

Defines the strict Redis payload structure.
NO frames, NO detection results, NO backend state.
"""

from dataclasses import dataclass
from typing import Literal
import time


# Priority levels represent OPERATIONAL URGENCY, not threat classification
PriorityLevel = Literal["critical", "high", "medium"]

# Redis queue mapping (operational priority)
REDIS_QUEUES = {
    "critical": "vg:critical",  # Fast-path processing
    "high": "vg:high",          # Normal processing priority
    "medium": "vg:medium"        # Low urgency processing
}


@dataclass
class TaskMetadata:
    """
    Redis task payload structure.
    
    This is the ONLY data sent to Redis queues.
    Frame data is stored in shared memory and referenced by key.
    """
    
    camera_id: str              # Unique camera identifier
    frame_id: str               # Unique frame identifier (timestamp-based)
    shared_memory_key: str      # Reference to frame in shared memory
    timestamp: float            # Unix timestamp when frame was captured
    priority: PriorityLevel     # Operational priority (NOT threat type)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis serialization."""
        return {
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "shared_memory_key": self.shared_memory_key,
            "timestamp": self.timestamp,
            "priority": self.priority
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TaskMetadata':
        """Create from dictionary (for deserialization)."""
        return cls(
            camera_id=data["camera_id"],
            frame_id=data["frame_id"],
            shared_memory_key=data["shared_memory_key"],
            timestamp=data["timestamp"],
            priority=data["priority"]
        )
    
    @staticmethod
    def generate_frame_id(camera_id: str) -> str:
        """Generate unique frame ID."""
        return f"{camera_id}_{int(time.time() * 1000000)}"
    
    def get_queue_name(self) -> str:
        """Get Redis queue name based on priority."""
        return REDIS_QUEUES[self.priority]
