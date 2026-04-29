"""
VisionGuard AI - System API Routes

Endpoints for system health, status, and metrics.
GET  /health
GET  /status
GET  /metrics
"""

import time
import os
import psutil
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
import redis

from ..core.config import get_settings, get_redis_config, Settings
from ..services.ecs_manager import get_ecs_manager, ECSManager
from ..services.camera_manager import get_camera_manager, CameraManager
from ..models.system import HealthResponse, StatusResponse, MetricsResponse, ComponentStatus
from ..utils.logging import get_logger
from ..utils.metrics_utils import aggregate_project_metrics

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


def get_directory_size(path: str) -> float:
    """Calculate total size of a directory in MB."""
    total_size = 0
    if not os.path.exists(path):
        return 0.0
    
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                # skip if it is symbolic link
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
    except Exception:
        pass
        
    # Convert to MB
    return round(total_size / (1024 * 1024), 1)


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
    
    # Fetch aggregated project-only metrics
    try:
        redis_config = get_redis_config()
        r_client = redis.Redis(**redis_config)
        project_metrics = aggregate_project_metrics(r_client)
        cpu_usage = project_metrics["cpu_usage"]
        memory_used = project_metrics["memory_used_gb"]
        r_client.close()
    except Exception:
        cpu_usage = 0.0
        memory_used = 0.0
        
    cpu_cores = psutil.cpu_count(logical=True)
    
    virtual_mem = psutil.virtual_memory()
    memory_total = round(virtual_mem.total / (1024 * 1024 * 1024), 2)
    
    shared_frames_dir = os.environ.get("SHARED_FRAMES_DIR", "/shared-frames")
    storage_used = get_directory_size(shared_frames_dir)
    
    # Storage total (approximate disk/volume size in MB)
    storage_total_override = os.environ.get("VG_STORAGE_TOTAL_MB")
    if storage_total_override:
        try:
            storage_total = float(storage_total_override)
        except ValueError:
            storage_total = 512000.0
    else:
        try:
            usage = psutil.disk_usage(shared_frames_dir)
            storage_total = round(usage.total / (1024 * 1024), 1)
        except Exception:
            storage_total = 512000.0  # Default to 512GB in MB
    
    return StatusResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + "Z",
        uptime_seconds=round(time.time() - _start_time, 2),
        components=components,
        cpu_usage=cpu_usage,
        cpu_cores=cpu_cores,
        memory_used_gb=memory_used,
        memory_total_gb=memory_total,
        storage_used_mb=storage_used,
        storage_total_mb=storage_total
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
