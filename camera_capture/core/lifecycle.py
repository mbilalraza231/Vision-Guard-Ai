"""
VisionGuard AI - Lifecycle Hooks

Clean hooks for FastAPI integration.
This is the public API that FastAPI imports and uses.
"""

from typing import Dict
import logging
from ..config import CaptureConfig
from .process_manager import ProcessManager

logger = logging.getLogger(__name__)


def start_cameras(config: CaptureConfig) -> ProcessManager:
    """
    Start all camera processes.
    
    This is the main entry point for FastAPI to start the camera capture module.
    
    Args:
        config: Complete capture configuration (injected by FastAPI)
        
    Returns:
        ProcessManager instance for controlling cameras
        
    Example:
        from camera_capture import start_cameras, CaptureConfig
        
        config = CaptureConfig(...)  # Load from file or construct
        manager = start_cameras(config)
    """
    manager = ProcessManager(config)
    manager.start_all()
    return manager


def stop_cameras(manager: ProcessManager, timeout: float = 10.0) -> None:
    """
    Stop all camera processes gracefully.
    
    Args:
        manager: ProcessManager instance returned by start_cameras()
        timeout: Maximum time to wait for processes to stop
        
    Example:
        stop_cameras(manager)
    """
    manager.stop_all(timeout=timeout)


def get_status(manager: ProcessManager) -> Dict[str, dict]:
    """
    Get status of all camera processes.
    
    Args:
        manager: ProcessManager instance
        
    Returns:
        Dictionary mapping camera_id to status info:
        {
            "camera_id": {
                "status": "alive" | "dead" | "stopped" | "error",
                "is_alive": bool,
                "pid": int | None
            }
        }
        
    Example:
        status = get_status(manager)
        for camera_id, info in status.items():
            logger.info("Camera status", extra={"camera_id": camera_id, "status": info.get("status")})
    """
    return manager.get_status()


def restart_camera(manager: ProcessManager, camera_id: str) -> bool:
    """
    Restart a specific camera process.
    
    Args:
        manager: ProcessManager instance
        camera_id: Camera ID to restart
        
    Returns:
        True if restart successful
        
    Example:
        if not restart_camera(manager, "cam_001"):
            logger.warning("Failed to restart camera")
    """
    return manager.restart_camera(camera_id)
