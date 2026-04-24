"""
VisionGuard AI - Frame Buffer

In-memory frame buffer with TTL management.
Single source of truth for frame correlation.
"""

import logging
import time
from typing import Dict, List, Optional
from .frame_state import FrameState, AIResult


class FrameBuffer:
    """
    In-memory frame buffer for ECS.
    
    Holds partial AI results keyed by frame_id.
    Manages TTL expiration and correlation window.
    
    This is the single source of truth for frame correlation.
    """
    
    def __init__(self):
        """Initialize frame buffer."""
        self.logger = logging.getLogger(__name__)
        
        # Frame buffer: frame_id -> FrameState
        self.frames: Dict[str, FrameState] = {}
        
        # Statistics
        self.frames_added = 0
        self.frames_removed = 0
        self.frames_expired = 0
        
        self.logger.info("Frame buffer initialized")
    
    def add_result(
        self,
        frame_id: str,
        camera_id: str,
        shared_memory_key: str,
        model_type: str,
        result: AIResult
    ) -> FrameState:
        """
        Add AI result to frame buffer.
        
        Creates new FrameState if frame_id doesn't exist.
        Updates existing FrameState if frame_id exists.
        
        Args:
            frame_id: Unique frame identifier
            camera_id: Camera identifier
            shared_memory_key: Shared memory key for cleanup
            model_type: Model type (weapon, fire, fall)
            result: AI inference result
            
        Returns:
            Updated FrameState
        """
        if frame_id not in self.frames:
            # Create new frame state
            frame_state = FrameState(
                frame_id=frame_id,
                camera_id=camera_id,
                shared_memory_key=shared_memory_key
            )
            self.frames[frame_id] = frame_state
            self.frames_added += 1
            
            self.logger.debug(
                f"Created new frame state",
                extra={
                    "frame_id": frame_id,
                    "camera_id": camera_id,
                    "model_type": model_type
                }
            )
        else:
            frame_state = self.frames[frame_id]
        
        # Add result to frame state
        frame_state.add_result(result)
        
        self.logger.debug(
            f"Added result to frame",
            extra={
                "frame_id": frame_id,
                "model_type": model_type,
                "confidence": result.confidence,
                "age_ms": frame_state.get_age_ms()
            }
        )
        
        return frame_state
    
    def get_frame(self, frame_id: str) -> Optional[FrameState]:
        """
        Get frame state by frame_id.
        
        Args:
            frame_id: Frame identifier
            
        Returns:
            FrameState if exists, None otherwise
        """
        return self.frames.get(frame_id)
    
    def remove_frame(self, frame_id: str) -> Optional[FrameState]:
        """
        Remove frame from buffer.
        
        Args:
            frame_id: Frame identifier
            
        Returns:
            Removed FrameState if existed, None otherwise
        """
        frame_state = self.frames.pop(frame_id, None)
        
        if frame_state:
            self.frames_removed += 1
            
            self.logger.debug(
                f"Removed frame from buffer",
                extra={
                    "frame_id": frame_id,
                    "age_ms": frame_state.get_age_ms()
                }
            )
        
        return frame_state
    
    def get_expired_frames(self, hard_ttl_seconds: float) -> List[FrameState]:
        """
        Get all expired frames.
        
        Args:
            hard_ttl_seconds: Hard TTL in seconds
            
        Returns:
            List of expired FrameState objects
        """
        expired = []
        
        for frame_state in self.frames.values():
            if frame_state.is_expired(hard_ttl_seconds):
                expired.append(frame_state)
        
        if expired:
            self.frames_expired += len(expired)
            
            self.logger.warning(
                f"Found {len(expired)} expired frames",
                extra={
                    "expired_count": len(expired),
                    "hard_ttl_seconds": hard_ttl_seconds
                }
            )
        
        return expired
    
    def get_frames_needing_classification(
        self, correlation_window_ms: int
    ) -> List[FrameState]:
        """
        Return frames that have aged past correlation_window_ms
        but have not yet been classified.
        Used for v2 periodic classification scan.
        
        Args:
            correlation_window_ms: Min age in ms before classification
            
        Returns:
            List of FrameState objects needing classification
        """
        now = time.time()
        result = []
        for frame_id, frame_state in self.frames.items():
            if frame_state.classification_attempted:
                continue
            age_ms = (now - frame_state.first_seen_ts) * 1000
            if age_ms >= correlation_window_ms:
                result.append(frame_state)
        return result
    
    def get_buffer_size(self) -> int:
        """
        Get current buffer size.
        
        Returns:
            Number of frames in buffer
        """
        return len(self.frames)
    
    def get_stats(self) -> dict:
        """
        Get buffer statistics.
        
        Returns:
            Dictionary with buffer stats
        """
        return {
            "current_size": len(self.frames),
            "frames_added": self.frames_added,
            "frames_removed": self.frames_removed,
            "frames_expired": self.frames_expired
        }
    
    def clear(self) -> None:
        """Clear all frames from buffer."""
        self.frames.clear()
        self.logger.info("Frame buffer cleared")
