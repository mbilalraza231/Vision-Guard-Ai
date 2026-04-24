"""
VisionGuard AI - ECS Lifecycle Hooks

Clean startup/shutdown hooks for backend control.
"""

from typing import Dict
import logging
from ..config import ECSConfig
from .service import ECSService

logger = logging.getLogger(__name__)


def start_ecs(config: ECSConfig) -> ECSService:
    """
    Start Event Classification Service.
    
    This is the main entry point for backend to start ECS.
    
    Args:
        config: ECS configuration
        
    Returns:
        ECSService instance for controlling the service
        
    Example:
        from event_classification import start_ecs, ECSConfig
        
        config = ECSConfig()
        ecs = start_ecs(config)
    """
    ecs = ECSService(config)
    ecs.start()
    return ecs


def stop_ecs(ecs: ECSService, timeout: float = 10.0) -> None:
    """
    Stop Event Classification Service gracefully.
    
    Args:
        ecs: ECSService instance returned by start_ecs()
        timeout: Maximum time to wait for service to stop
        
    Example:
        stop_ecs(ecs)
    """
    ecs.stop(timeout=timeout)


def get_ecs_status(ecs: ECSService) -> Dict[str, any]:
    """
    Get ECS status.
    
    Args:
        ecs: ECSService instance
        
    Returns:
        Dictionary with status info:
        {
            "is_alive": bool,
            "pid": int | None
        }
        
    Example:
        status = get_ecs_status(ecs)
        if not status["is_alive"]:
            logger.warning("ECS is dead, restarting...")
    """
    return {
        "is_alive": ecs.is_alive(),
        "pid": ecs.process.pid if ecs.process else None
    }
