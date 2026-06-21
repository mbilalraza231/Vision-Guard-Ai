"""
VisionGuard AI - Frame Compressor

Provides utilities to compress numpy arrays to JPEG/WebP bytes and decompress them.
Supports optional CLAHE (contrast enhancement) and Gaussian denoising applied
once in the shared preprocessing pipeline so all AI workers benefit.
"""

import cv2
import numpy as np


def apply_enhancements(
    frame: np.ndarray,
    enable_clahe: bool = False,
    enable_denoising: bool = False,
) -> np.ndarray:
    """
    Apply optional image enhancements to a BGR uint8 frame.

    Operations (applied in order when enabled):
      1. CLAHE — adaptive histogram equalisation on the L channel of LAB
         colour space.  Improves contrast in dark / unevenly-lit scenes.
      2. Gaussian Denoising — mild 3×3 Gaussian blur to reduce sensor noise.
         Fast and non-destructive; preserves edges well at this kernel size.

    Both operations keep the frame as BGR uint8 so it remains compatible
    with cv2.imencode, cv2.imdecode, and the clip recorder.

    Args:
        frame (np.ndarray): OpenCV BGR uint8 image.
        enable_clahe (bool): Apply CLAHE contrast enhancement.
        enable_denoising (bool): Apply Gaussian blur denoising.

    Returns:
        np.ndarray: Enhanced BGR uint8 image (same shape/dtype as input).
    """
    if enable_clahe:
        # Convert BGR → LAB, apply CLAHE to L channel only, convert back
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        lab = cv2.merge((l_ch, a_ch, b_ch))
        frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    if enable_denoising:
        # 3×3 Gaussian blur — fast, mild noise reduction, no float32 conversion
        frame = cv2.GaussianBlur(frame, (3, 3), 0)

    return frame


def compress_frame(frame: np.ndarray, format: str = "jpeg", quality: int = 95) -> bytes:
    """
    Compress a numpy array frame to the specified format.

    Args:
        frame (np.ndarray): OpenCV BGR image as numpy array.
        format (str): 'jpeg' or 'webp'.
        quality (int): Compression quality (1-100).

    Returns:
        bytes: Encoded bytes.
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
        data (bytes): Raw bytes.

    Returns:
        bool: True if the data appears to be a compressed image (JPEG or WebP).
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
        data (bytes): Compressed image bytes.

    Returns:
        np.ndarray: OpenCV BGR image as numpy array.
    """
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise RuntimeError("Failed to decompress frame from bytes")

    return frame


def resize_and_compress_frame(
    frame: np.ndarray,
    sizes: list[int],
    format: str = "jpeg",
    quality: int = 95,
    enable_clahe: bool = False,
    enable_denoising: bool = False,
) -> dict[int, bytes]:
    """
    Optionally enhance, then resize a frame to multiple dimensions and compress each.

    Enhancements (CLAHE / denoising) are applied ONCE to the original-resolution
    frame before resizing so the cost is paid only once regardless of how many
    size variants are generated.

    Args:
        frame (np.ndarray): Original OpenCV BGR image as numpy array.
        sizes (list[int]): List of target widths (e.g., [640, 416]).
        format (str): Compression format ('jpeg' or 'webp').
        quality (int): Compression quality (1-100).
        enable_clahe (bool): Apply CLAHE contrast enhancement before resize.
        enable_denoising (bool): Apply Gaussian denoising before resize.

    Returns:
        dict[int, bytes]: Dictionary mapping size → compressed bytes.
    """
    # Apply enhancements once at full resolution before generating size variants
    if enable_clahe or enable_denoising:
        frame = apply_enhancements(frame, enable_clahe=enable_clahe, enable_denoising=enable_denoising)

    results = {}
    for size in sizes:
        if frame.shape[:2] != (size, size):
            resized = cv2.resize(frame, (size, size), interpolation=cv2.INTER_LINEAR)
        else:
            resized = frame

        results[size] = compress_frame(resized, format=format, quality=quality)

    return results
