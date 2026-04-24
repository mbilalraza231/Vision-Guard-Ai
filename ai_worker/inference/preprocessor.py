"""
VisionGuard AI - Frame Preprocessor

CPU-only frame preprocessing for YOLOv8 ONNX inference.
Resize to model input size, normalize to [0,1] via /255, transpose to NCHW.

NOTE: YOLOv8 expects ONLY /255 normalization — no ImageNet mean/std.
"""

import cv2
import numpy as np
import logging
from typing import Tuple


class Preprocessor:
    """
    Frame preprocessor for YOLOv8 ONNX models.
    
    CPU-only operations using NumPy and OpenCV.
    Standard YOLOv8 preprocessing: resize → BGR2RGB → /255 → CHW → batch.
    """
    
    def __init__(self, target_size: Tuple[int, int] = (640, 640)):
        """
        Initialize preprocessor.
        
        Args:
            target_size: Target size (width, height) for model input
        """
        self.target_size = target_size
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(
            f"Preprocessor initialized",
            extra={"target_size": target_size}
        )
    
    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Preprocess frame for YOLOv8 ONNX inference.
        
        Steps:
        1. Resize to target size
        2. Convert BGR to RGB
        3. Normalize to [0, 1] via /255.0
        4. Transpose to (C, H, W)
        5. Add batch dimension
        
        Args:
            frame: Input frame (BGR, uint8)
            
        Returns:
            Preprocessed tensor (1, C, H, W) float32, values in [0, 1]
        """
        try:
            # Resize
            if frame.shape[:2] != (self.target_size[1], self.target_size[0]):
                resized = cv2.resize(frame, self.target_size, interpolation=cv2.INTER_LINEAR)
            else:
                resized = frame
            
            # Convert BGR to RGB
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            
            # Normalize to [0, 1] — YOLOv8 standard preprocessing
            # NO ImageNet mean/std normalization
            normalized = rgb.astype(np.float32) / 255.0
            
            # Transpose to (C, H, W)
            transposed = np.transpose(normalized, (2, 0, 1))
            
            # Add batch dimension (1, C, H, W)
            batched = np.expand_dims(transposed, axis=0)
            
            return batched
            
        except Exception as e:
            self.logger.error(
                f"Preprocessing failed: {e}",
                extra={"error": str(e), "frame_shape": frame.shape}
            )
            raise
