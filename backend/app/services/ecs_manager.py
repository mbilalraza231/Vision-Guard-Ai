"""
VisionGuard AI - ECS Manager Service

Manages the Event Classification Service lifecycle.
This is the ONLY way to control ECS from the backend.

ECS runs as a separate process - backend does NOT perform classification.
"""

import sys
import os
from typing import Optional, Dict, Any
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from ..core.supervisor import ProcessSupervisor, ProcessState
from ..core.config import get_settings, get_ecs_config
from ..utils.logging import get_logger

logger = get_logger(__name__)


def _ecs_process_target(config_dict: dict) -> None:
    """
    Target function for ECS subprocess.
    
    This runs in a separate process and imports ECS to avoid
    any import side effects in the main backend process.
    """
    # Import ECS inside the subprocess
    from event_classification import ECSConfig
    from event_classification.core.service import ECSService
    
    # Create config from dict
    config = ECSConfig(**config_dict)
    
    # Create and start service
    service = ECSService(config)
    service.start()
    if service.process:
        service.process.join()


class ECSManager:
    """
    Manages ECS lifecycle from the backend.
    
    Responsibilities:
    - Start ECS as a subprocess
    - Stop ECS gracefully
    - Monitor ECS health
    - Provide status information
    
    Does NOT:
    - Perform classification
    - Consume Redis streams
    - Touch shared memory
    """
    
    _instance: Optional['ECSManager'] = None
    
    def __new__(cls):
        """Singleton pattern - only one ECS manager."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._supervisor = ProcessSupervisor("ECS")
        self._config: Optional[dict] = None
        self._start_time: Optional[datetime] = None
        self.logger = get_logger(__name__)
        self._initialized = True

    def _runtime_block_message(self) -> str:
        return (
            "ECS lifecycle control is disabled in docker runtime mode. "
            "Manage ECS container lifecycle via docker compose."
        )
    
    async def start(self, config_override: dict = None) -> Dict[str, Any]:
        """
        Start the ECS process.
        
        Args:
            config_override: Optional config values to override defaults
            
        Returns:
            Status dictionary with result
        """
        settings = get_settings()
        if not settings.allow_local_process_control:
            return {
                "success": False,
                "message": self._runtime_block_message(),
                "status": self.get_status()
            }

        # Get config
        config = get_ecs_config()
        if config_override:
            config.update(config_override)
        
        self._config = config
        
        self.logger.info("Starting ECS process...")
        
        success = await self._supervisor.start(
            target=_ecs_process_target,
            args=(config,),
            timeout=settings.ecs_start_timeout
        )
        
        if success:
            self._start_time = datetime.now()
            return {
                "success": True,
                "message": "ECS started successfully",
                "status": self._supervisor.get_status()
            }
        else:
            return {
                "success": False,
                "message": f"Failed to start ECS: {self._supervisor.info.last_error}",
                "status": self._supervisor.get_status()
            }
    
    async def stop(self) -> Dict[str, Any]:
        """
        Stop the ECS process gracefully.
        
        Returns:
            Status dictionary with result
        """
        settings = get_settings()
        if not settings.allow_local_process_control:
            return {
                "success": False,
                "message": self._runtime_block_message(),
                "status": self.get_status()
            }
        
        self.logger.info("Stopping ECS process...")
        
        success = await self._supervisor.stop(timeout=settings.ecs_stop_timeout)
        
        if success:
            return {
                "success": True,
                "message": "ECS stopped successfully",
                "status": self._supervisor.get_status()
            }
        else:
            return {
                "success": False,
                "message": f"Failed to stop ECS: {self._supervisor.info.last_error}",
                "status": self._supervisor.get_status()
            }
    
    async def restart(self) -> Dict[str, Any]:
        """
        Restart the ECS process.
        
        Returns:
            Status dictionary with result
        """
        settings = get_settings()
        if not settings.allow_local_process_control:
            return {
                "success": False,
                "message": self._runtime_block_message(),
                "status": self.get_status()
            }

        self.logger.info("Restarting ECS process...")
        
        # Stop first
        stop_result = await self.stop()
        if not stop_result["success"]:
            return {
                "success": False,
                "message": f"Restart failed during stop: {stop_result['message']}",
                "status": self._supervisor.get_status()
            }
        
        # Start again
        start_result = await self.start(self._config)
        if start_result["success"]:
            self._supervisor.info.restart_count += 1
        
        return start_result
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current ECS status.
        
        Returns:
            Comprehensive status dictionary
        """
        status = self._supervisor.get_status()
        settings = get_settings()
        
        # Add ECS-specific info
        status["config"] = self._config
        status["manager_start_time"] = (
            self._start_time.isoformat() if self._start_time else None
        )
        status["runtime_mode"] = settings.runtime_mode
        status["local_process_control_enabled"] = settings.allow_local_process_control
        
        return status
    
    def is_running(self) -> bool:
        """Check if ECS is running."""
        return self._supervisor.check_health()
    
    @property
    def state(self) -> ProcessState:
        """Get current ECS state."""
        self._supervisor.check_health()
        return self._supervisor.info.state


# Global singleton instance
_ecs_manager: Optional[ECSManager] = None


def get_ecs_manager() -> ECSManager:
    """Get the ECS manager singleton."""
    global _ecs_manager
    if _ecs_manager is None:
        _ecs_manager = ECSManager()
    return _ecs_manager
