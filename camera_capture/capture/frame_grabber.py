"""
VisionGuard AI - Frame Grabber

Controls frame capture rate with FPS throttling.
"""

import time
import logging
from typing import Optional
import cv2


class FrameGrabber:
    """
    FPS-controlled frame grabber.
    
    Throttles frame capture to configured FPS to prevent overwhelming
    downstream systems.
    """
    
    def __init__(self, fps: int = 5, camera_id: str = "unknown"):
        """
        Initialize frame grabber.
        
        Args:
            fps: Target frames per second (1-30)
            camera_id: Camera identifier for logging
        """
        if fps < 1 or fps > 30:
            raise ValueError("FPS must be between 1 and 30")
        
        self.fps = fps
        self.camera_id = camera_id
        self.frame_interval = 1.0 / fps
        self.logger = logging.getLogger(__name__)
        
        self.last_capture_time = 0.0
        self.frames_captured = 0
        self.frames_skipped = 0
    
    def should_capture(self) -> bool:
        """
        Check if enough time has passed to capture next frame.
        
        Returns:
            True if frame should be captured, False if should skip
        """
        current_time = time.time()
        time_since_last = current_time - self.last_capture_time
        
        if time_since_last >= self.frame_interval:
            return True
        else:
            self.frames_skipped += 1
            return False
    
    def mark_captured(self) -> None:
        """Mark that a frame was captured (updates timing)."""
        self.last_capture_time = time.time()
        self.frames_captured += 1
    
    def wait_for_next_frame(self) -> None:
        """
        Sleep until it's time for the next frame.
        
        Useful for precise FPS control in tight loops.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_capture_time
        
        if time_since_last < self.frame_interval:
            sleep_time = self.frame_interval - time_since_last
            time.sleep(sleep_time)
    
    def get_stats(self) -> dict:
        """
        Get frame grabber statistics.
        
        Returns:
            Dictionary with fps, frames_captured, frames_skipped, actual_fps
        """
        # Calculate actual FPS
        if self.last_capture_time > 0:
            elapsed_time = time.time() - self.last_capture_time
            actual_fps = self.frames_captured / elapsed_time if elapsed_time > 0 else 0.0
        else:
            actual_fps = 0.0
        
        return {
            "target_fps": self.fps,
            "frames_captured": self.frames_captured,
            "frames_skipped": self.frames_skipped,
            "actual_fps": round(actual_fps, 2)
        }
    
    def reset(self) -> None:
        """Reset statistics."""
        self.last_capture_time = 0.0
        self.frames_captured = 0
        self.frames_skipped = 0
        
        self.logger.debug(
            f"Frame grabber reset",
            extra={"camera_id": self.camera_id}
        )
