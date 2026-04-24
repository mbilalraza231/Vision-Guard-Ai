"""
VisionGuard AI - Camera Capture Module

Public API for FastAPI integration.

This module provides low-level camera ingestion services:
- Multi-camera RTSP capture
- Motion detection
- Shared memory frame storage
- Redis task queue production

NO business logic, NO AI inference, NO HTTP endpoints.
"""

# Public API exports
from .config import (
    CaptureConfig,
    CameraConfig,
    RedisConfig,
    SharedMemoryConfig,
    RetryConfig,
    BufferConfig,
    LoggingConfig
)

from .core.lifecycle import (
    start_cameras,
    stop_cameras,
    get_status,
    restart_camera
)

from .core.process_manager import ProcessManager

__version__ = "1.0.0"

__all__ = [
    # Configuration models
    "CaptureConfig",
    "CameraConfig",
    "RedisConfig",
    "SharedMemoryConfig",
    "RetryConfig",
    "BufferConfig",
    "LoggingConfig",
    
    # Lifecycle functions (main API)
    "start_cameras",
    "stop_cameras",
    "get_status",
    "restart_camera",
    
    # Process manager (for advanced usage)
    "ProcessManager",
]
