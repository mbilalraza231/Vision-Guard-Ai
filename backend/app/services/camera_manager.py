"""
VisionGuard AI - Camera Manager Service

Manages camera capture pipelines from the backend.
Provides registration, start/stop, and status APIs.
"""

import sys
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from ..core.config import get_settings
from ..core.database import db
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CameraInfo:
    """Information about a registered camera."""
    camera_id: str
    rtsp_url: str
    fps: int = 5
    motion_threshold: float = 0.02
    enabled: bool = True
    is_running: bool = False
    registered_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    frames_captured: int = 0
    frames_with_motion: int = 0
    last_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "camera_id": self.camera_id,
            "rtsp_url": self.rtsp_url,
            "fps": self.fps,
            "motion_threshold": self.motion_threshold,
            "enabled": self.enabled,
            "is_running": self.is_running,
            "registered_at": self.registered_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "frames_captured": self.frames_captured,
            "frames_with_motion": self.frames_with_motion,
            "last_error": self.last_error,
        }


class CameraManager:
    """
    Manages camera capture pipelines.
    
    Responsibilities:
    - Register camera configurations
    - Start/stop camera capture processes
    - Monitor camera health
    - Provide status information
    
    Integrates with camera_capture module when cameras are started.
    """
    
    _instance: Optional['CameraManager'] = None
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._cameras: Dict[str, CameraInfo] = {}
        self._process_manager = None  # Will hold camera_capture ProcessManager
        self.logger = get_logger(__name__)
        
        # Load from config if available (especially for Docker mode status reporting)
        self.load_from_config()
        
        self._initialized = True

    def load_from_config(self) -> None:
        """Load cameras from cameras.json if it exists."""
        import json
        config_path = os.environ.get("CAMERA_CONFIG_PATH", "cameras.json")
        
        # In docker, the directory is often /app/backend but cameras.json is at /app/cameras.json
        if not os.path.exists(config_path):
            alt_path = os.path.join("..", config_path)
            if os.path.exists(alt_path):
                config_path = alt_path
            else:
                # Try absolute path if we can determine project root
                try:
                    from ..core.config import get_settings
                    settings = get_settings()
                    # Check in project root
                    root_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cameras.json")
                    if os.path.exists(root_path):
                        config_path = root_path
                except:
                    pass

        if not os.path.exists(config_path):
            self.logger.debug(f"Camera config not found at {config_path}")
            return
            
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
                cameras_data = data.get("cameras", [])
                
                for cam_data in cameras_data:
                    camera_id = cam_data.get("id")
                    if not camera_id:
                        continue
                        
                    camera = CameraInfo(
                        camera_id=camera_id,
                        rtsp_url=cam_data.get("source", ""),
                        fps=cam_data.get("fps", 5),
                        motion_threshold=cam_data.get("motion_threshold", 0.02),
                        enabled=cam_data.get("enabled", True)
                    )
                    # For status reporting, we assume it might be running if enabled in docker
                    # Real running status should ideally be verified via Redis heartbeats
                    self._cameras[camera_id] = camera
                    
            self.logger.info(f"Loaded {len(self._cameras)} cameras from {config_path}")
        except Exception as e:
            self.logger.error(f"Failed to load camera config: {e}")

    def _runtime_block_message(self) -> str:
        return (
            "Camera process lifecycle control is disabled in docker runtime mode. "
            "Manage camera service lifecycle via docker compose and cameras.json."
        )
    
    def register(
        self,
        camera_id: str,
        rtsp_url: str,
        fps: int = None,
        motion_threshold: float = None
    ) -> Dict[str, Any]:
        """
        Register a new camera.
        
        Args:
            camera_id: Unique camera identifier
            rtsp_url: RTSP stream URL
            fps: Frames per second (optional, uses default)
            motion_threshold: Motion detection threshold (optional)
            
        Returns:
            Registration result
        """
        settings = get_settings()
        
        if camera_id in self._cameras:
            return {
                "success": False,
                "message": f"Camera {camera_id} already registered",
                "camera": self._cameras[camera_id].to_dict()
            }
        
        camera = CameraInfo(
            camera_id=camera_id,
            rtsp_url=rtsp_url,
            fps=fps or settings.default_camera_fps,
            motion_threshold=motion_threshold or settings.default_motion_threshold
        )
        
        self._cameras[camera_id] = camera
        
        self.logger.info(f"Registered camera: {camera_id}")
        
        return {
            "success": True,
            "message": f"Camera {camera_id} registered",
            "camera": camera.to_dict()
        }
    
    def unregister(self, camera_id: str) -> Dict[str, Any]:
        """
        Unregister a camera.
        
        Camera must be stopped before unregistering.
        """
        if camera_id not in self._cameras:
            return {
                "success": False,
                "message": f"Camera {camera_id} not found"
            }
        
        camera = self._cameras[camera_id]
        if camera.is_running:
            return {
                "success": False,
                "message": f"Camera {camera_id} is running, stop it first"
            }
        
        del self._cameras[camera_id]
        
        self.logger.info(f"Unregistered camera: {camera_id}")
        
        return {
            "success": True,
            "message": f"Camera {camera_id} unregistered"
        }
    
    async def start_camera(self, camera_id: str) -> Dict[str, Any]:
        """
        Start a registered camera.
        
        Args:
            camera_id: Camera to start
            
        Returns:
            Start result
        """
        if camera_id not in self._cameras:
            return {
                "success": False,
                "message": f"Camera {camera_id} not found"
            }

        settings = get_settings()
        if not settings.allow_local_process_control:
            return {
                "success": False,
                "message": self._runtime_block_message(),
                "camera": self._cameras[camera_id].to_dict()
            }
        
        camera = self._cameras[camera_id]
        
        if camera.is_running:
            return {
                "success": True,
                "message": f"Camera {camera_id} already running",
                "camera": camera.to_dict()
            }
        
        try:
            # Import camera_capture to start the camera
            from camera_capture import start_cameras, CaptureConfig, CameraConfig
            
            # Create config for single camera
            config = CaptureConfig(
                cameras=[
                    CameraConfig(
                        camera_id=camera.camera_id,
                        rtsp_url=camera.rtsp_url,
                        fps=camera.fps,
                        motion_threshold=camera.motion_threshold
                    )
                ]
            )
            
            # Start camera process
            # Note: This starts the camera in a subprocess
            self._process_manager = start_cameras(config)
            
            camera.is_running = True
            camera.started_at = datetime.now()
            camera.last_error = None
            
            self.logger.info(f"Started camera: {camera_id}")
            
            return {
                "success": True,
                "message": f"Camera {camera_id} started",
                "camera": camera.to_dict()
            }
            
        except Exception as e:
            camera.last_error = str(e)
            self.logger.error(f"Failed to start camera {camera_id}: {e}")
            
            return {
                "success": False,
                "message": f"Failed to start camera: {e}",
                "camera": camera.to_dict()
            }
    
    async def stop_camera(self, camera_id: str) -> Dict[str, Any]:
        """
        Stop a running camera.
        
        Args:
            camera_id: Camera to stop
            
        Returns:
            Stop result
        """
        if camera_id not in self._cameras:
            return {
                "success": False,
                "message": f"Camera {camera_id} not found"
            }

        settings = get_settings()
        if not settings.allow_local_process_control:
            return {
                "success": False,
                "message": self._runtime_block_message(),
                "camera": self._cameras[camera_id].to_dict()
            }
        
        camera = self._cameras[camera_id]
        
        if not camera.is_running:
            return {
                "success": True,
                "message": f"Camera {camera_id} already stopped",
                "camera": camera.to_dict()
            }
        
        try:
            # Import camera_capture to stop
            from camera_capture import stop_cameras
            
            if self._process_manager:
                stop_cameras(self._process_manager, timeout=settings.camera_stop_timeout)
                self._process_manager = None
            
            camera.is_running = False
            camera.stopped_at = datetime.now()
            
            self.logger.info(f"Stopped camera: {camera_id}")
            
            return {
                "success": True,
                "message": f"Camera {camera_id} stopped",
                "camera": camera.to_dict()
            }
            
        except Exception as e:
            camera.last_error = str(e)
            self.logger.error(f"Failed to stop camera {camera_id}: {e}")
            
            return {
                "success": False,
                "message": f"Failed to stop camera: {e}",
                "camera": camera.to_dict()
            }
    
    async def start_all(self) -> Dict[str, Any]:
        """Start all registered cameras."""
        results = {}
        for camera_id in self._cameras:
            results[camera_id] = await self.start_camera(camera_id)
        
        success_count = sum(1 for r in results.values() if r["success"])
        
        return {
            "success": success_count == len(self._cameras),
            "message": f"Started {success_count}/{len(self._cameras)} cameras",
            "results": results
        }
    
    async def stop_all(self) -> Dict[str, Any]:
        """Stop all running cameras."""
        results = {}
        for camera_id in self._cameras:
            if self._cameras[camera_id].is_running:
                results[camera_id] = await self.stop_camera(camera_id)
        
        return {
            "success": True,
            "message": f"Stopped {len(results)} cameras",
            "results": results
        }
    
    def get_camera_status(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific camera."""
        if camera_id not in self._cameras:
            return None
        return self._cameras[camera_id].to_dict()
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all cameras."""
        settings = get_settings()
        
        # In docker mode, we check Redis heartbeat for the camera service
        is_service_alive = False
        if settings.is_docker_runtime:
            try:
                from ..core.config import get_redis_config
                from ..utils.metrics_utils import check_service_liveness
                import redis
                
                r_config = get_redis_config()
                r_client = redis.Redis(**r_config)
                is_service_alive = check_service_liveness(r_client, "camera")
                r_client.close()
            except Exception:
                pass

        cameras = {}
        running_count = 0
        
        for cid, cam in self._cameras.items():
            cam_dict = cam.to_dict()
            
            # If service is alive and camera is enabled, consider it running in Docker mode
            if settings.is_docker_runtime and is_service_alive and cam.enabled:
                cam_dict["is_running"] = True
                running_count += 1
                
                # Try to get REAL FPS from Redis
                try:
                    from ..core.config import get_redis_config
                    import redis
                    r_config = get_redis_config()
                    r_client = redis.Redis(**r_config)
                    fps_val = r_client.get(f"vg:metrics:camera:{cid}:fps")
                    if fps_val:
                        cam_dict["fps_actual"] = float(fps_val.decode('utf-8'))
                    r_client.close()
                except Exception:
                    pass
            elif cam.is_running:
                running_count += 1
                
            cameras[cid] = cam_dict
        
        return {
            "total": len(self._cameras),
            "running": running_count,
            "stopped": len(self._cameras) - running_count,
            "cameras": cameras,
            "service_alive": is_service_alive if settings.is_docker_runtime else None
        }
    
    async def sync_db_to_json(self) -> None:
        """Write all cameras in the database to cameras.json to keep them in sync."""
        import json
        config_path = os.environ.get("CAMERA_CONFIG_PATH", "cameras.json")
        if not os.path.isabs(config_path):
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), config_path)
            
        try:
            # Fetch all cameras from database
            rows = await db.fetch_all("SELECT id, name, source, fps, motion_threshold, priority, enabled FROM cameras ORDER BY id ASC")
            cameras_list = []
            for r in rows:
                cameras_list.append({
                    "id": r["id"],
                    "name": r["name"],
                    "source": r["source"],
                    "fps": r["fps"],
                    "motion_threshold": r["motion_threshold"],
                    "priority": r["priority"],
                    "enabled": r["enabled"]
                })
            
            # Read current cameras.json to preserve global and ip_camera sections
            global_conf = {"motion_detection": True, "default_fps": 5, "reconnect_delay_sec": 5}
            ip_camera_conf = {"username": "YOUR_USERNAME", "password": "YOUR_PASSWORD", "ip_address": "192.168.X.X", "port": 554}
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        curr = json.load(f)
                        if "global" in curr:
                            global_conf = curr["global"]
                        if "ip_camera" in curr:
                            ip_camera_conf = curr["ip_camera"]
                except Exception:
                    pass
                    
            output_data = {
                "cameras": cameras_list,
                "global": global_conf,
                "ip_camera": ip_camera_conf
            }
            
            with open(config_path, "w") as f:
                json.dump(output_data, f, indent=4)
            self.logger.info(f"Synchronized database cameras to {config_path}")
        except Exception as e:
            self.logger.error(f"Failed to sync database to cameras.json: {e}")

    async def seed_from_json_if_empty(self) -> None:
        """If database cameras are empty, seed them from cameras.json."""
        try:
            # Seed from JSON
            import json
            import time
            config_path = os.environ.get("CAMERA_CONFIG_PATH", "cameras.json")
            if not os.path.isabs(config_path):
                config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), config_path)
                
            if os.path.exists(config_path):
                # Check if actually empty
                existing = await db.fetch_all("SELECT id FROM cameras LIMIT 1")
                if existing:
                    return
                    
                self.logger.info(f"Seeding cameras table from {config_path}...")
                with open(config_path, "r") as f:
                    data = json.load(f)
                    cameras_data = data.get("cameras", [])
                        
                    for c in cameras_data:
                        cid = c.get("id") or c.get("camera_id")
                        if not cid:
                            continue
                        await db.execute(
                            """
                            INSERT INTO cameras (id, name, source, fps, motion_threshold, priority, enabled, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (id) DO NOTHING
                            """,
                            cid,
                            c.get("name", cid),
                            c.get("source", c.get("rtsp_url", "")),
                            c.get("fps", 5),
                            c.get("motion_threshold", 0.02),
                            c.get("priority", "medium"),
                            c.get("enabled", True),
                            time.time()
                        )
                self.logger.info("Database seeding completed.")
        except Exception as e:
            self.logger.error(f"Failed to seed database from cameras.json: {e}")

    def list_cameras(self) -> List[str]:
        """Get list of registered camera IDs."""
        return list(self._cameras.keys())


# Global singleton instance
_camera_manager: Optional[CameraManager] = None


def get_camera_manager() -> CameraManager:
    """Get the camera manager singleton."""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager
