"""
VisionGuard AI - Frame Manager

READ-ONLY shared memory access for AI workers.
NO cleanup - Event Classification Service owns frame lifecycle.
"""

import logging
import sys
import os

# Import from camera_capture module
from camera_capture.storage.shared_memory_impl import SharedMemoryImpl
import numpy as np
from typing import Optional


class FrameManager:
    """
    Frame manager for AI workers.
    
    CRITICAL: AI Worker is READ-ONLY for shared memory.
    - Reads frames using shared_memory_key
    - NEVER cleans up frames
    - Event Classification Service owns cleanup
    """
    
    def __init__(self, max_frame_size_mb: int = 10):
        """
        Initialize frame manager.
        
        Args:
            max_frame_size_mb: Maximum frame size in MB
        """
        self.logger = logging.getLogger(__name__)
        
        # Reuse camera module's shared memory implementation
        self.shared_memory = SharedMemoryImpl(max_frame_size_mb=max_frame_size_mb)
        
        # Statistics
        self.frames_read = 0
        self.read_failures = 0
        
        self.logger.info(
            "Frame manager initialized (READ-ONLY mode)",
            extra={"max_frame_size_mb": max_frame_size_mb}
        )
    
    def read_frame(self, shared_memory_key: str) -> Optional[np.ndarray]:
        """
        Read frame from shared memory (READ-ONLY).
        
        Args:
            shared_memory_key: Unique key from task metadata
            
        Returns:
            Frame as NumPy array, or None if not found
        """
        try:
            frame = self.shared_memory.read_frame(shared_memory_key)
            
            if frame is not None:
                self.frames_read += 1
                
                self.logger.debug(
                    f"Read frame from shared memory",
                    extra={
                        "shared_memory_key": shared_memory_key,
                        "frame_shape": frame.shape
                    }
                )
            else:
                self.read_failures += 1
                
                self.logger.warning(
                    f"Frame not found in shared memory",
                    extra={"shared_memory_key": shared_memory_key}
                )
            
            return frame
            
        except Exception as e:
            self.read_failures += 1
            
            self.logger.error(
                f"Error reading frame from shared memory: {e}",
                extra={
                    "shared_memory_key": shared_memory_key,
                    "error": str(e)
                }
            )
            return None
    
    def cleanup(self, shared_memory_key: str) -> None:
        """
        DEFENSIVE: Cleanup should NEVER be called by AI worker.
        
        This method logs a warning if called.
        Event Classification Service owns frame cleanup.
        
        Args:
            shared_memory_key: Key to cleanup (SHOULD NOT BE CALLED)
        """
        self.logger.error(
            "CRITICAL: AI Worker attempted to cleanup shared memory! "
            "This violates the architecture. Event Classification Service owns cleanup.",
            extra={
                "shared_memory_key": shared_memory_key,
                "violation": "ai_worker_cleanup_attempt"
            }
        )
        
        # DO NOT actually cleanup - this is a defensive check
        # Event Classification Service is responsible for cleanup
    
    def get_stats(self) -> dict:
        """
        Get frame manager statistics.
        
        Returns:
            Dictionary with frames_read, read_failures
        """
        return {
            "frames_read": self.frames_read,
            "read_failures": self.read_failures,
            "mode": "READ_ONLY"
        }
