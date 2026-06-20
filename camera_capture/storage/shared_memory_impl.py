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

        # Grant world write/delete permissions so non-root containers can delete frames.
        # Use 0o777 (NOT 0o1777 sticky bit) — sticky bit prevents non-root users
        # from deleting files owned by other users (e.g., camera=root, ECS=vguser).
        try:
            os.chmod(self.shared_dir, 0o777)
        except PermissionError:
            self._logger.debug(
                f"Could not chmod {self.shared_dir} (expected if not root)")

        # On Docker, named volumes may have restrictive default permissions.
        # Attempt to remove sticky bit explicitly if present, since it blocks
        # cross-container file deletion (camera=root creates files, ECS=vguser deletes).
        try:
            stat_info = os.stat(self.shared_dir)
            mode = stat_info.st_mode
            if mode & 0o1000:  # sticky bit is set
                os.chmod(self.shared_dir, mode & ~0o1000)  # remove sticky bit
                self._logger.info(f"Removed sticky bit from {self.shared_dir}")
        except (PermissionError, OSError):
            pass  # Non-root or read-only FS — proceed anyway

        # Dtype mapping for serialization
        self._dtype_map = {
            np.uint8: 0,
            np.float32: 1,
            np.float64: 2,
        }
        self._dtype_reverse_map = {v: k for k, v in self._dtype_map.items()}

    def write_frame(self, frame: np.ndarray, compressed_bytes: Optional[bytes] = None, custom_key: Optional[str] = None) -> str:
        """
        Write frame to shared storage.

        Returns:
            Unique key (UUID-based)

        Raises:
            MemoryError: If frame is too large or write fails
        """
        # Calculate required size
        if compressed_bytes is not None:
            total_size = len(compressed_bytes)
        else:
            # Validate frame
            if not isinstance(frame, np.ndarray):
                raise ValueError("Frame must be a NumPy array")

            if frame.dtype.type not in self._dtype_map:
                raise ValueError(
                    f"Unsupported dtype: {frame.dtype}. Supported: {list(self._dtype_map.keys())}")
            
            header_size = 16  # 4 ints: height, width, channels, dtype
            frame_size = frame.nbytes
            total_size = header_size + frame_size

        if total_size > self.max_frame_size_bytes:
            raise MemoryError(
                f"Frame size ({total_size} bytes) exceeds maximum "
                f"({self.max_frame_size_bytes} bytes). Skipping frame."
            )

        # Generate or use provided unique key
        key = custom_key if custom_key else str(uuid.uuid4())
        filepath = os.path.join(self.shared_dir, key)

        try:
            tmp_path = filepath + ".tmp"
            with open(tmp_path, 'wb') as f:
                if compressed_bytes is not None:
                    f.write(compressed_bytes)
                else:
                    # Build frame data with header
                    height, width = frame.shape[:2]
                    channels = frame.shape[2] if len(frame.shape) == 3 else 1
                    dtype_code = self._dtype_map[frame.dtype.type]

                    header = struct.pack('IIII', height, width, channels, dtype_code)
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
                data = f.read()

            if not data:
                return None
                
            # Attempt to auto-decompress if it's a compressed image
            try:
                import sys
                # Ensure project root is in sys.path to find preprocessing module
                if os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) not in sys.path:
                    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                from preprocessing.resize_and_compress import is_compressed, decompress_frame
                
                if is_compressed(data):
                    frame = decompress_frame(data)
                    self._logger.debug(
                        f"Read compressed frame from shared storage",
                        extra={"shared_memory_key": key, "shape": frame.shape}
                    )
                    return frame
            except ImportError as e:
                self._logger.warning(f"preprocessing module not found: {e}")
            except Exception as e:
                self._logger.error(f"Error checking/decompressing frame: {e}")
                
            # Legacy raw numpy array format
            header_data = data[:16]
            if len(header_data) < 16:
                raise ValueError("Incomplete header")

            height, width, channels, dtype_code = struct.unpack(
                'IIII', header_data)

            # Validate dtype
            if dtype_code not in self._dtype_reverse_map:
                raise ValueError(f"Invalid dtype code: {dtype_code}")

            dtype = self._dtype_reverse_map[dtype_code]

            # Read frame data
            frame_bytes = data[16:]

            # Reconstruct frame
            if channels == 1:
                frame = np.frombuffer(
                    frame_bytes, dtype=dtype).reshape(height, width)
            else:
                frame = np.frombuffer(frame_bytes, dtype=dtype).reshape(
                    height, width, channels)

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
            file_count = len([f for f in os.listdir(
                self.shared_dir) if not f.endswith('.tmp')])
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
