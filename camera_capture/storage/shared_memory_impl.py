"""
VisionGuard AI - Shared Memory Implementation

File-based shared storage using a shared tmpfs volume (/shared-frames).
This avoids conflicts with Python's multiprocessing semaphores in /dev/shm.
Thread-safe and multi-process safe.
"""

import numpy as np
import os
import threading
from typing import Optional, Dict
import uuid
import struct
import logging
from .shared_memory_interface import SharedMemoryInterface


# Default shared directory for frame storage (tmpfs volume in Docker)
SHARED_FRAMES_DIR = os.environ.get("SHARED_FRAMES_DIR", "/shared-frames")


class SharedMemoryImpl(SharedMemoryInterface):
    """
    File-based shared storage implementation.
    
    Uses a shared tmpfs volume for cross-container frame sharing.
    This avoids /dev/shm conflicts with Python's multiprocessing semaphores.
    
    Frame format:
    [4 bytes: height][4 bytes: width][4 bytes: channels][4 bytes: dtype][frame data]
    """
    
    def __init__(self, max_frame_size_mb: int = 10, shared_dir: str = None):
        """
        Initialize shared memory manager.
        
        Args:
            max_frame_size_mb: Maximum size per frame in MB
            shared_dir: Directory for shared frame files (default: /shared-frames)
        """
        self.max_frame_size_bytes = max_frame_size_mb * 1024 * 1024
        self.shared_dir = shared_dir or SHARED_FRAMES_DIR
        self._active_keys: Dict[str, str] = {}  # key -> filepath
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)
        
        # Ensure shared directory exists
        os.makedirs(self.shared_dir, exist_ok=True)
        
        # Dtype mapping for serialization
        self._dtype_map = {
            np.uint8: 0,
            np.float32: 1,
            np.float64: 2,
        }
        self._dtype_reverse_map = {v: k for k, v in self._dtype_map.items()}
    
    def write_frame(self, frame: np.ndarray) -> str:
        """
        Write frame to shared storage.
        
        Returns:
            Unique key (UUID-based)
            
        Raises:
            MemoryError: If frame is too large or write fails
        """
        # Validate frame
        if not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a NumPy array")
        
        if frame.dtype.type not in self._dtype_map:
            raise ValueError(f"Unsupported dtype: {frame.dtype}. Supported: {list(self._dtype_map.keys())}")
        
        # Calculate required size
        header_size = 16  # 4 ints: height, width, channels, dtype
        frame_size = frame.nbytes
        total_size = header_size + frame_size
        
        if total_size > self.max_frame_size_bytes:
            raise MemoryError(
                f"Frame size ({total_size} bytes) exceeds maximum "
                f"({self.max_frame_size_bytes} bytes). Skipping frame."
            )
        
        # Generate unique key
        key = str(uuid.uuid4())
        filepath = os.path.join(self.shared_dir, key)
        
        try:
            # Build frame data with header
            height, width = frame.shape[:2]
            channels = frame.shape[2] if len(frame.shape) == 3 else 1
            dtype_code = self._dtype_map[frame.dtype.type]
            
            header = struct.pack('IIII', height, width, channels, dtype_code)
            
            # Write atomically: write to temp file, then rename
            tmp_path = filepath + ".tmp"
            with open(tmp_path, 'wb') as f:
                f.write(header)
                f.write(frame.tobytes())
            
            # Make world-readable for cross-container access
            os.chmod(tmp_path, 0o666)
            os.rename(tmp_path, filepath)
            
            # Track reference
            with self._lock:
                self._active_keys[key] = filepath
            
            self._logger.debug(
                f"Wrote frame to shared storage",
                extra={"shared_memory_key": key, "size_bytes": total_size}
            )
            
            return key
            
        except Exception as e:
            self._logger.error(
                f"Failed to write frame: {e}",
                extra={"error": str(e)}
            )
            # Cleanup on failure
            for p in [filepath, filepath + ".tmp"]:
                try:
                    os.unlink(p)
                except OSError:
                    pass
            raise MemoryError(f"Failed to write frame: {e}")
    
    def read_frame(self, key: str) -> Optional[np.ndarray]:
        """
        Read frame from shared storage.
        
        Used by AI workers (not camera module).
        """
        filepath = os.path.join(self.shared_dir, key)
        
        try:
            with open(filepath, 'rb') as f:
                # Read header
                header_data = f.read(16)
                if len(header_data) < 16:
                    raise ValueError("Incomplete header")
                
                height, width, channels, dtype_code = struct.unpack('IIII', header_data)
                
                # Validate dtype
                if dtype_code not in self._dtype_reverse_map:
                    raise ValueError(f"Invalid dtype code: {dtype_code}")
                
                dtype = self._dtype_reverse_map[dtype_code]
                
                # Read frame data
                frame_size = height * width * channels * np.dtype(dtype).itemsize
                frame_bytes = f.read(frame_size)
            
            # Reconstruct frame
            if channels == 1:
                frame = np.frombuffer(frame_bytes, dtype=dtype).reshape(height, width)
            else:
                frame = np.frombuffer(frame_bytes, dtype=dtype).reshape(height, width, channels)
            
            self._logger.debug(
                f"Read frame from shared storage",
                extra={"shared_memory_key": key, "shape": frame.shape}
            )
            
            return frame
            
        except FileNotFoundError:
            self._logger.warning(
                f"Shared memory key not found: {key}",
                extra={"shared_memory_key": key}
            )
            return None
        except Exception as e:
            self._logger.error(
                f"Failed to read frame: {e}",
                extra={"shared_memory_key": key, "error": str(e)}
            )
            return None
    
    def cleanup(self, key: str) -> None:
        """
        Release shared frame file.
        
        Safe to call multiple times.
        """
        with self._lock:
            self._active_keys.pop(key, None)
        
        filepath = os.path.join(self.shared_dir, key)
        try:
            os.unlink(filepath)
            self._logger.debug(
                f"Cleaned up shared frame",
                extra={"shared_memory_key": key}
            )
        except FileNotFoundError:
            pass  # Already cleaned up
        except Exception as e:
            self._logger.warning(
                f"Error during cleanup: {e}",
                extra={"shared_memory_key": key, "error": str(e)}
            )
    
    def get_stats(self) -> dict:
        """Get shared storage statistics."""
        with self._lock:
            total_blocks = len(self._active_keys)
        
        # Count actual files in shared dir
        try:
            file_count = len([f for f in os.listdir(self.shared_dir) if not f.endswith('.tmp')])
        except OSError:
            file_count = 0
        
        return {
            "total_blocks": total_blocks,
            "active_blocks": file_count,
            "memory_used_mb": 0  # Would need to sum file sizes
        }
    
    def cleanup_all(self) -> None:
        """Cleanup all shared frame files. Called on shutdown."""
        with self._lock:
            keys = list(self._active_keys.keys())
        
        for key in keys:
            self.cleanup(key)
        
        self._logger.info("Cleaned up all shared frame files")
