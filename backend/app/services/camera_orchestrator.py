"""
VisionGuard AI - Camera Orchestrator

Abstracts the starting and stopping of camera capture processes 
away from the API, handling both Local and Docker runtimes seamlessly.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from datetime import datetime
from ..utils.logging import get_logger
from ..core.config import get_settings

logger = get_logger(__name__)


class CameraOrchestrator(ABC):
    """
    Abstract base class for camera orchestration strategies.
    """

    @abstractmethod
    async def start_camera(self, camera_manager: Any, camera: Any) -> Dict[str, Any]:
        """
        Start the camera capture process.
        
        Args:
            camera_manager: The CameraManager instance
            camera: The CameraInfo instance to start
            
        Returns:
            Dict containing success status and message
        """
        pass

    @abstractmethod
    async def stop_camera(self, camera_manager: Any, camera: Any) -> Dict[str, Any]:
        """
        Stop the camera capture process.
        
        Args:
            camera_manager: The CameraManager instance
            camera: The CameraInfo instance to stop
            
        Returns:
            Dict containing success status and message
        """
        pass


class LocalCameraOrchestrator(CameraOrchestrator):
    """
    Orchestrates cameras by directly spawning local multiprocessing processes.
    Used when running outside of Docker.
    """

    async def start_camera(self, camera_manager: Any, camera: Any) -> Dict[str, Any]:
        try:
            # Import camera_capture to start the camera locally
            from camera_capture import start_cameras, CaptureConfig, CameraConfig
            
            # Create config for single camera
            config = CaptureConfig(
                cameras=[
                    CameraConfig(
                        camera_id=camera.camera_id,
                        rtsp_url=camera.rtsp_url,
                        fps=camera.fps,
                        motion_threshold=camera.motion_threshold,
                        process_mode=getattr(camera, 'process_mode', 'live'),
                    )
                ]
            )
            
            # Start camera process
            camera_manager._process_manager = start_cameras(config)
            
            camera.is_running = True
            camera.started_at = datetime.now()
            camera.last_error = None
            
            logger.info(f"Started local camera process: {camera.camera_id}")
            
            return {
                "success": True,
                "message": f"Camera {camera.camera_id} started locally",
                "camera": camera.to_dict()
            }
            
        except Exception as e:
            camera.last_error = str(e)
            logger.error(f"Failed to start local camera {camera.camera_id}: {e}")
            
            return {
                "success": False,
                "message": f"Failed to start local camera: {e}",
                "camera": camera.to_dict()
            }

    async def stop_camera(self, camera_manager: Any, camera: Any) -> Dict[str, Any]:
        try:
            from camera_capture import stop_cameras
            
            if camera_manager._process_manager:
                settings = get_settings()
                stop_cameras(camera_manager._process_manager, timeout=settings.camera_stop_timeout)
                camera_manager._process_manager = None
            
            camera.is_running = False
            camera.stopped_at = datetime.now()
            
            logger.info(f"Stopped local camera process: {camera.camera_id}")
            
            return {
                "success": True,
                "message": f"Camera {camera.camera_id} stopped locally",
                "camera": camera.to_dict()
            }
            
        except Exception as e:
            camera.last_error = str(e)
            logger.error(f"Failed to stop local camera {camera.camera_id}: {e}")
            
            return {
                "success": False,
                "message": f"Failed to stop local camera: {e}",
                "camera": camera.to_dict()
            }


class DockerCameraOrchestrator(CameraOrchestrator):
    """
    Orchestrates cameras by simply acknowledging the configuration change.
    The actual `vg-camera` container watches `cameras.json` via a watchdog 
    and handles its own internal lifecycle asynchronously.
    """

    async def start_camera(self, camera_manager: Any, camera: Any) -> Dict[str, Any]:
        logger.info(f"Docker mode: Sent start configuration for camera {camera.camera_id}")
        return {
            "success": True,
            "message": f"Camera {camera.camera_id} enabled for Docker runtime. Watchdog will apply shortly.",
            "camera": camera.to_dict()
        }

    async def stop_camera(self, camera_manager: Any, camera: Any) -> Dict[str, Any]:
        logger.info(f"Docker mode: Sent stop configuration for camera {camera.camera_id}")
        return {
            "success": True,
            "message": f"Camera {camera.camera_id} disabled for Docker runtime. Watchdog will apply shortly.",
            "camera": camera.to_dict()
        }


def get_orchestrator() -> CameraOrchestrator:
    """Factory to get the correct orchestrator based on settings."""
    settings = get_settings()
    if settings.is_docker_runtime:
        return DockerCameraOrchestrator()
    else:
        return LocalCameraOrchestrator()
