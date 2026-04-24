"""
VisionGuard AI - Process Manager

Orchestrates multiple camera processes.
Provides clean interface for FastAPI control.
"""

import logging
from typing import Dict, List, Optional
from ..config import CaptureConfig
from .camera_process import CameraProcess


class ProcessManager:
    """
    Multi-camera process manager.
    
    Responsibilities:
    - Spawn one process per camera
    - Track process health (alive/dead/reconnecting)
    - Graceful shutdown of all processes
    - Detect process crashes and report status as "dead"
    - NO auto-restart logic (FastAPI decides whether to restart)
    """
    
    def __init__(self, config: CaptureConfig):
        """
        Initialize process manager.
        
        Args:
            config: Complete capture configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Camera processes
        self.processes: Dict[str, CameraProcess] = {}
        
        # Status tracking
        self.status: Dict[str, str] = {}  # camera_id -> status
    
    def start_all(self) -> Dict[str, bool]:
        """
        Start all camera processes.
        
        Returns:
            Dictionary mapping camera_id to start success (True/False)
        """
        results = {}
        
        self.logger.info(
            f"Starting {len(self.config.cameras)} camera processes",
            extra={"camera_count": len(self.config.cameras)}
        )
        
        for camera_config in self.config.cameras:
            camera_id = camera_config.camera_id
            
            try:
                # Create camera process
                process = CameraProcess(
                    camera_config=camera_config,
                    redis_config=self.config.redis,
                    buffer_config=self.config.buffer,
                    retry_config=self.config.retry,
                    shared_memory_config=self.config.shared_memory,
                    log_level=self.config.logging.level,
                    log_format=self.config.logging.format
                )
                
                # Start process
                success = process.start()
                
                if success:
                    self.processes[camera_id] = process
                    self.status[camera_id] = "alive"
                    results[camera_id] = True
                    
                    self.logger.info(
                        f"Started camera process",
                        extra={"camera_id": camera_id}
                    )
                else:
                    self.status[camera_id] = "failed_to_start"
                    results[camera_id] = False
                    
                    self.logger.error(
                        f"Failed to start camera process",
                        extra={"camera_id": camera_id}
                    )
                    
            except Exception as e:
                self.status[camera_id] = "error"
                results[camera_id] = False
                
                self.logger.error(
                    f"Error starting camera process: {e}",
                    extra={"camera_id": camera_id, "error": str(e)}
                )
        
        return results
    
    def stop_all(self, timeout: float = 10.0) -> None:
        """
        Stop all camera processes gracefully.
        
        Args:
            timeout: Maximum time to wait per process
        """
        self.logger.info(
            f"Stopping {len(self.processes)} camera processes",
            extra={"process_count": len(self.processes)}
        )
        
        for camera_id, process in self.processes.items():
            try:
                self.logger.info(
                    f"Stopping camera process",
                    extra={"camera_id": camera_id}
                )
                
                process.stop(timeout=timeout)
                self.status[camera_id] = "stopped"
                
            except Exception as e:
                self.logger.error(
                    f"Error stopping camera process: {e}",
                    extra={"camera_id": camera_id, "error": str(e)}
                )
        
        self.processes.clear()
        self.logger.info("All camera processes stopped")
    
    def get_status(self) -> Dict[str, dict]:
        """
        Get status of all camera processes.
        
        Returns:
            Dictionary mapping camera_id to status info:
            {
                "camera_id": {
                    "status": "alive" | "dead" | "stopped" | "error",
                    "is_alive": bool,
                    "pid": int | None
                }
            }
        """
        status_info = {}
        
        for camera_id in self.status.keys():
            process = self.processes.get(camera_id)
            
            if process:
                is_alive = process.is_alive()
                
                # Update status based on actual process state
                if is_alive:
                    current_status = "alive"
                else:
                    # Process crashed or stopped
                    if self.status[camera_id] == "alive":
                        # Was alive, now dead = crashed
                        current_status = "dead"
                        self.logger.warning(
                            f"Camera process crashed",
                            extra={"camera_id": camera_id}
                        )
                    else:
                        current_status = self.status[camera_id]
                
                self.status[camera_id] = current_status
                
                status_info[camera_id] = {
                    "status": current_status,
                    "is_alive": is_alive,
                    "pid": process.process.pid if process.process else None
                }
            else:
                status_info[camera_id] = {
                    "status": self.status.get(camera_id, "unknown"),
                    "is_alive": False,
                    "pid": None
                }
        
        return status_info
    
    def restart_camera(self, camera_id: str) -> bool:
        """
        Restart a specific camera process.
        
        Note: This is called by FastAPI, not automatically by this module.
        
        Args:
            camera_id: Camera ID to restart
            
        Returns:
            True if restart successful
        """
        self.logger.info(
            f"Restarting camera process",
            extra={"camera_id": camera_id}
        )
        
        # Stop existing process
        if camera_id in self.processes:
            try:
                self.processes[camera_id].stop()
            except Exception as e:
                self.logger.warning(
                    f"Error stopping process during restart: {e}",
                    extra={"camera_id": camera_id, "error": str(e)}
                )
        
        # Find camera config
        camera_config = None
        for config in self.config.cameras:
            if config.camera_id == camera_id:
                camera_config = config
                break
        
        if not camera_config:
            self.logger.error(
                f"Camera config not found for restart",
                extra={"camera_id": camera_id}
            )
            return False
        
        # Create and start new process
        try:
            process = CameraProcess(
                camera_config=camera_config,
                redis_config=self.config.redis,
                buffer_config=self.config.buffer,
                retry_config=self.config.retry,
                shared_memory_config=self.config.shared_memory,
                log_level=self.config.logging.level,
                log_format=self.config.logging.format
            )
            
            success = process.start()
            
            if success:
                self.processes[camera_id] = process
                self.status[camera_id] = "alive"
                
                self.logger.info(
                    f"Camera process restarted successfully",
                    extra={"camera_id": camera_id}
                )
                return True
            else:
                self.status[camera_id] = "failed_to_restart"
                self.logger.error(
                    f"Failed to restart camera process",
                    extra={"camera_id": camera_id}
                )
                return False
                
        except Exception as e:
            self.status[camera_id] = "error"
            self.logger.error(
                f"Error restarting camera process: {e}",
                extra={"camera_id": camera_id, "error": str(e)}
            )
            return False
    
    def get_camera_ids(self) -> List[str]:
        """Get list of all camera IDs."""
        return list(self.status.keys())
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.stop_all(timeout=5.0)
        except:
            pass
