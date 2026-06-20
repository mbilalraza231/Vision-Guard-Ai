"""
VisionGuard AI - Frame Compressor

Provides utilities to compress numpy arrays to JPEG/WebP bytes and decompress them.
"""

import cv2
import numpy as np

def compress_frame(frame: np.ndarray, format: str = "jpeg", quality: int = 95) -> bytes:
    """
    Compress a numpy array frame to the specified format.
    
    Args:
        frame: OpenCV BGR image as numpy array.
        format: 'jpeg' or 'webp'.
        quality: Compression quality (1-100).
        
    Returns:
        Encoded bytes.
    """
    if format.lower() == "jpeg":
        success, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    elif format.lower() == "webp":
        success, encoded = cv2.imencode('.webp', frame, [int(cv2.IMWRITE_WEBP_QUALITY), quality])
    else:
        raise ValueError(f"Unsupported compression format: {format}")
        
    if not success:
        raise RuntimeError(f"Failed to compress frame to {format}")
        
    return encoded.tobytes()

def is_compressed(data: bytes) -> bool:
    """
    Check if the byte array is a compressed image by inspecting magic bytes.
    
    Args:
        data: Raw bytes.
        
    Returns:
        True if the data appears to be a compressed image (JPEG or WebP).
    """
    if not data:
        return False
        
    # Check JPEG magic bytes (\xff\xd8\xff)
    if len(data) >= 3 and data.startswith(b'\xff\xd8\xff'):
        return True
        
    # Check WebP magic bytes (RIFF....WEBP)
    if len(data) >= 12 and data[0:4] == b'RIFF' and data[8:12] == b'WEBP':
        return True
        
    return False

def decompress_frame(data: bytes) -> np.ndarray:
    """
    Decompress image bytes back to a numpy array.
    
    Args:
        data: Compressed image bytes.
        
    Returns:
        OpenCV BGR image as numpy array.
    """
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        raise RuntimeError("Failed to decompress frame from bytes")
        
    return frame

def resize_and_compress_frame(frame: np.ndarray, sizes: list[int], format: str = "jpeg", quality: int = 95) -> dict[int, bytes]:
    """
    Resize a frame to multiple square dimensions and compress each.
    
    Args:
        frame: Original OpenCV BGR image as numpy array.
        sizes: List of target widths/heights (e.g., [640, 416]).
        format: Compression format ('jpeg' or 'webp').
        quality: Compression quality.
        
    Returns:
        Dictionary mapping size to compressed bytes.
    """
    results = {}
    for size in sizes:
        # Resize using cv2.resize (simple resize to match AI worker preprocessor behavior)
        if frame.shape[:2] != (size, size):
            resized = cv2.resize(frame, (size, size), interpolation=cv2.INTER_LINEAR)
        else:
            resized = frame
            
        results[size] = compress_frame(resized, format=format, quality=quality)
        
    return results
