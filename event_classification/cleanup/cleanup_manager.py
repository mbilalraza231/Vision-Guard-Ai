"""
VisionGuard AI - Cleanup Manager

Authoritative shared memory cleanup for ECS.
ECS is the ONLY component allowed to free shared memory.
"""

import logging
from typing import Set

# Import shared memory implementation from camera_capture
from camera_capture.storage.shared_memory_impl import SharedMemoryImpl



class CleanupManager:
    """
    Shared memory cleanup manager.
    
    CRITICAL: ECS is the ONLY component allowed to free shared memory.
    AI workers are READ-ONLY.
    
    Cleanup triggers:
    1. Frame TTL expires
    2. Classification completes
    3. Frame is discarded
    
    REFINEMENT: Idempotent cleanup with tracking to avoid double-cleanup logs.
    """
    
    def __init__(self, max_frame_size_mb: int = 10):
        """
        Initialize cleanup manager.
        
        Args:
            max_frame_size_mb: Maximum frame size in MB
        """
        self.logger = logging.getLogger(__name__)
        
        # Reuse camera module's shared memory implementation
        self.shared_memory = SharedMemoryImpl(max_frame_size_mb=max_frame_size_mb)
        
        # REFINEMENT: Track cleaned keys to avoid double-cleanup logs
        self.cleaned_keys: Set[str] = set()
        
        # Statistics
        self.cleanup_attempts = 0
        self.cleanup_successes = 0
        self.cleanup_failures = 0
        self.cleanup_duplicates = 0
        
        self.logger.info(
            "Cleanup manager initialized (AUTHORITATIVE)",
            extra={"max_frame_size_mb": max_frame_size_mb}
        )
    
    def cleanup_frame(self, shared_memory_key: str) -> bool:
        """
        Cleanup frame from shared memory.
        
        REFINEMENT: Idempotent - tracks cleaned keys to avoid duplicate cleanup.
        
        Args:
            shared_memory_key: Shared memory key to cleanup
            
        Returns:
            True if cleanup successful or already cleaned
        """
        self.cleanup_attempts += 1
        
        # REFINEMENT: Check if already cleaned (idempotency)
        if shared_memory_key in self.cleaned_keys:
            self.cleanup_duplicates += 1
            
            self.logger.debug(
                f"Frame already cleaned (idempotent)",
                extra={"shared_memory_key": shared_memory_key}
            )
            
            return True
        
        try:
            # Cleanup shared memory
            self.shared_memory.cleanup(shared_memory_key)
            
            # Mark as cleaned
            self.cleaned_keys.add(shared_memory_key)
            self.cleanup_successes += 1
            
            self.logger.info(
                f"Cleaned up frame from shared memory",
                extra={"shared_memory_key": shared_memory_key}
            )
            
            return True
            
        except FileNotFoundError:
            # Frame already freed or never existed
            self.logger.warning(
                f"Frame not found (already cleaned or never existed)",
                extra={"shared_memory_key": shared_memory_key}
            )
            # Mark as cleaned to avoid retry
            self.cleaned_keys.add(shared_memory_key)
            self.cleanup_successes += 1
            return True
            
        except PermissionError as e:
            # Permission issue - log but mark as cleaned to avoid retry loops
            self.cleanup_failures += 1
            self.logger.error(
                f"Permission denied during cleanup: {e}",
                extra={
                    "shared_memory_key": shared_memory_key,
                    "error": str(e)
                }
            )
            # Mark as cleaned to prevent retry loops
            self.cleaned_keys.add(shared_memory_key)
            return False
            
        except Exception as e:
            self.cleanup_failures += 1
            
            self.logger.error(
                f"Cleanup failed: {e}",
                extra={
                    "shared_memory_key": shared_memory_key,
                    "error": str(e)
                },
                exc_info=True
            )
            
            # REFINEMENT: Mark as cleaned to prevent infinite retry loops
            # Cleanup failure should NOT block buffer eviction
            self.cleaned_keys.add(shared_memory_key)
            return False
    
    def get_stats(self) -> dict:
        """
        Get cleanup statistics.
        
        Returns:
            Dictionary with cleanup stats
        """
        return {
            "cleanup_attempts": self.cleanup_attempts,
            "cleanup_successes": self.cleanup_successes,
            "cleanup_failures": self.cleanup_failures,
            "cleanup_duplicates": self.cleanup_duplicates,
            "cleaned_keys_count": len(self.cleaned_keys)
        }
    
    def clear_tracking(self) -> None:
        """
        Clear cleaned keys tracking.
        
        Call periodically to prevent unbounded memory growth.
        """
        self.cleaned_keys.clear()
        self.logger.info("Cleared cleanup tracking")
