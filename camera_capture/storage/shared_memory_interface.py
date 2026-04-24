"""
VisionGuard AI - Shared Memory Interface

Abstract interface for shared memory operations.
Defines the contract for both camera module (write) and AI workers (read).
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Optional


class SharedMemoryInterface(ABC):
    """
    Abstract interface for shared memory operations.
    
    This interface is implemented by the camera module but defines
    the complete contract that AI workers will also use.
    """
    
    @abstractmethod
    def write_frame(self, frame: np.ndarray) -> str:
        """
        Write frame to shared memory.
        
        Args:
            frame: NumPy array containing the frame data
            
        Returns:
            Unique key referencing the shared memory block
            
        Raises:
            MemoryError: If shared memory is full
        """
        pass
    
    @abstractmethod
    def read_frame(self, key: str) -> Optional[np.ndarray]:
        """
        Read frame from shared memory by key.
        
        This method is used by AI workers (not implemented in camera module yet).
        Defined now to freeze the API contract.
        
        Args:
            key: Unique key returned by write_frame()
            
        Returns:
            NumPy array containing the frame data, or None if key not found
            
        Raises:
            ValueError: If key is invalid
        """
        pass
    
    @abstractmethod
    def cleanup(self, key: str) -> None:
        """
        Release shared memory block.
        
        Args:
            key: Unique key to cleanup
            
        Note:
            Safe to call multiple times with the same key.
            Safe to call with non-existent keys (no-op).
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> dict:
        """
        Get shared memory statistics.
        
        Returns:
            Dictionary with keys: total_blocks, active_blocks, memory_used_mb
        """
        pass
