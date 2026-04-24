"""
VisionGuard AI - System API Routes

Endpoints for system health, status, and metrics.
GET  /health
GET  /status
GET  /metrics
"""

import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
import redis

from ..core.config import get_settings, get_redis_config, Settings
from ..services.ecs_manager import get_ecs_manager, ECSManager
from ..services.camera_manager import get_camera_manager, CameraManager
from ..models.system import HealthResponse, StatusResponse, MetricsResponse, ComponentStatus
from ..utils.logging import get_logger

router = APIRouter(tags=["System"])
logger = get_logger(__name__)

# Application start time for uptime calculation
_start_time = time.time()


def check_redis_health() -> Dict[str, Any]:
    """Check Redis connectivity and return status."""
    try:
        config = get_redis_config()
        client = redis.Redis(**config, socket_connect_timeout=2)
        info = client.info("server")
        
        # Check queue lengths
        queue_lengths = {
            "vg:critical": client.llen("vg:critical"),
            "vg:high": client.llen("vg:high"),
            "vg:medium": client.llen("vg:medium"),
        }
        
        # Check stream length
        stream_length = client.xlen("vg:ai:results")
        
        client.close()
        
        return {
            "status": "connected",
            "version": info.get("redis_version", "unknown"),
            "queues": queue_lengths,
            "stream_length": stream_length
        }
    except redis.ConnectionError as e:
        return {
            "status": "disconnected",
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/health", response_model=HealthResponse)
async def health_check(
    settings: Settings = Depends(get_settings)
) -> HealthResponse:
    """
    Liveness check endpoint.
    
    Returns basic health status for load balancers and orchestration.
    Always returns 200 if the API is responding.
    """
    # Fast health check - just check if we're alive
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version=settings.app_version
    )


@router.get("/status", response_model=StatusResponse)
async def system_status(
    ecs_manager: ECSManager = Depends(get_ecs_manager),
    camera_manager: CameraManager = Depends(get_camera_manager),
    settings: Settings = Depends(get_settings)
) -> StatusResponse:
    """
    Comprehensive system status.
    
    Returns status of all components: ECS, Redis, Cameras.
    Used for monitoring dashboards.
    """
    # Get component statuses
    ecs_status = ecs_manager.get_status()
    redis_status = check_redis_health()
    camera_status = camera_manager.get_all_status()
    
    # Build component map
    components = {
        "ecs": ComponentStatus(
            name="Event Classification Service",
            status=ecs_status.get("state", "unknown"),
            details=ecs_status
        ),
        "redis": ComponentStatus(
            name="Redis",
            status=redis_status.get("status", "unknown"),
            details=redis_status
        ),
        "cameras": ComponentStatus(
            name="Cameras",
            status=f"{camera_status['running']}/{camera_status['total']} running",
            details=camera_status
        )
    }
    
    # Determine overall status
    # - healthy: all components operational
    # - degraded: some components down but system usable
    # - unhealthy: critical components down
    
    if redis_status.get("status") != "connected":
        overall_status = "unhealthy"
    elif ecs_status.get("state") != "running":
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    return StatusResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + "Z",
        uptime_seconds=round(time.time() - _start_time, 2),
        components=components
    )


@router.get("/metrics", response_model=MetricsResponse)
async def system_metrics(
    ecs_manager: ECSManager = Depends(get_ecs_manager),
    camera_manager: CameraManager = Depends(get_camera_manager),
    settings: Settings = Depends(get_settings)
) -> MetricsResponse:
    """
    System metrics for monitoring.
    
    Returns operational metrics for Prometheus/Grafana integration.
    """
    ecs_status = ecs_manager.get_status()
    camera_status = camera_manager.get_all_status()
    redis_status = check_redis_health()
    
    return MetricsResponse(
        timestamp=datetime.utcnow().isoformat() + "Z",
        system={
            "uptime_seconds": round(time.time() - _start_time, 2),
            "environment": settings.environment,
            "version": settings.app_version,
        },
        ecs={
            "state": ecs_status.get("state"),
            "uptime_seconds": ecs_status.get("uptime_seconds", 0),
            "restart_count": ecs_status.get("restart_count", 0),
        },
        cameras={
            "total": camera_status["total"],
            "running": camera_status["running"],
            "stopped": camera_status["stopped"],
        },
        redis=redis_status
    )
