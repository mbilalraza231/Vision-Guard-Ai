"""
VisionGuard AI - Motion Detection

Fast background subtraction for motion detection.
Filters out static frames before expensive AI inference.
"""

import cv2
import numpy as np
import logging
from typing import Optional


class MotionDetector:
    """
    Lightweight motion detector using background subtraction.
    
    Performance requirement: Must be significantly cheaper than AI inference
    and suitable for real-time CPU processing.
    """
    
    def __init__(
        self,
        threshold: float = 0.02,
        history: int = 500,
        var_threshold: int = 16,
        detect_shadows: bool = False
    ):
        """
        Initialize motion detector.
        
        Args:
            threshold: Motion threshold (0.0-1.0, percentage of frame with motion)
            history: Number of frames for background model
            var_threshold: Variance threshold for background subtraction
            detect_shadows: Whether to detect shadows (slower if enabled)
        """
        self.threshold = threshold
        self.logger = logging.getLogger(__name__)
        
        # Use MOG2 background subtractor (fast and effective)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=detect_shadows
        )
        
        # Statistics
        self.frames_processed = 0
        self.motion_detected_count = 0
    
    def detect(self, frame: np.ndarray) -> bool:
        """
        Detect motion in frame.
        
        Args:
            frame: Input frame (BGR or grayscale)
            
        Returns:
            True if motion detected (above threshold), False otherwise
        """
        if frame is None or frame.size == 0:
            return False
        
        # Apply background subtraction
        fg_mask = self.bg_subtractor.apply(frame)
        
        # Calculate motion percentage
        total_pixels = fg_mask.shape[0] * fg_mask.shape[1]
        motion_pixels = np.count_nonzero(fg_mask)
        motion_percentage = motion_pixels / total_pixels
        
        # Update statistics
        self.frames_processed += 1
        
        # Check threshold
        has_motion = motion_percentage >= self.threshold
        
        if has_motion:
            self.motion_detected_count += 1
            self.logger.debug(
                f"Motion detected",
                extra={
                    "motion_percentage": round(motion_percentage, 4),
                    "threshold": self.threshold
                }
            )
        
        return has_motion
    
    def get_stats(self) -> dict:
        """
        Get motion detection statistics.
        
        Returns:
            Dictionary with frames_processed, motion_detected_count, detection_rate
        """
        detection_rate = (
            self.motion_detected_count / self.frames_processed
            if self.frames_processed > 0
            else 0.0
        )
        
        return {
            "frames_processed": self.frames_processed,
            "motion_detected_count": self.motion_detected_count,
            "detection_rate": round(detection_rate, 4)
        }
    
    def reset(self) -> None:
        """Reset background model and statistics."""
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=16,
            detectShadows=False
        )
        self.frames_processed = 0
        self.motion_detected_count = 0
        
        self.logger.info("Motion detector reset")
