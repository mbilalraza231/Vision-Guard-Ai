"""
VisionGuard AI - Application Lifecycle Management

Startup and shutdown hooks for the FastAPI application.
Manages graceful initialization and cleanup of all services.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from .config import get_settings
from ..services.ecs_manager import get_ecs_manager
from ..services.camera_manager import get_camera_manager
from ..utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.
    
    Handles:
    - Startup: Initialize logging, validate config, warm up services
    - Shutdown: Stop ECS, stop cameras, cleanup resources
    
    Does NOT auto-start ECS or cameras - that's done via API calls.
    """
    settings = get_settings()
    
    # ========== STARTUP ==========
    logger.info("="*60)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info("="*60)
    
    # Initialize logging
    setup_logging(
        level=settings.log_level,
        format_type=settings.log_format
    )
    
    # Initialize service managers (lazy - don't start anything)
    ecs_manager = get_ecs_manager()
    camera_manager = get_camera_manager()
    
    logger.info("Service managers initialized")
    logger.info(f"Backend ready at http://{settings.host}:{settings.port}")
    
    # Yield control to application
    yield
    
    # ========== SHUTDOWN ==========
    logger.info("Shutting down application...")

    if not settings.allow_local_process_control:
        logger.info("Docker runtime mode detected; skipping local process shutdown hooks")
        logger.info("Shutdown complete")
        return
    
    # Stop ECS if running
    if ecs_manager.is_running():
        logger.info("Stopping ECS...")
        await ecs_manager.stop()
    
    # Stop all cameras
    camera_status = camera_manager.get_all_status()
    if camera_status["running"] > 0:
        logger.info(f"Stopping {camera_status['running']} cameras...")
        await camera_manager.stop_all()
    
    logger.info("Shutdown complete")


async def check_dependencies() -> dict:
    """
    Check all external dependencies.
    
    Returns dict with status of each dependency.
    """
    import redis
    from .config import get_redis_config
    
    results = {"redis": False, "ecs_module": False, "camera_module": False}
    
    # Check Redis
    try:
        config = get_redis_config()
        client = redis.Redis(**config, socket_connect_timeout=2)
        client.ping()
        client.close()
        results["redis"] = True
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
    
    # Check ECS module
    try:
        from event_classification import ECSConfig
        results["ecs_module"] = True
    except ImportError:
        logger.warning("ECS module not available")
    
    # Check camera module
    try:
        from camera_capture import CaptureConfig
        results["camera_module"] = True
    except ImportError:
        logger.warning("Camera module not available")
    
    return results
