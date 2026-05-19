"""
VisionGuard AI - Camera API Routes

Endpoints for camera registration and control.
GET  /cameras           ← NEW: merged camera list from cameras.json + runtime status
POST /cameras/register
POST /cameras/{id}/start
POST /cameras/{id}/stop
GET  /cameras/status
GET  /cameras/{id}/status
DELETE /cameras/{id}
"""

import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam

from ..services.camera_manager import get_camera_manager, CameraManager
from ..models.cameras import (
    CameraRegisterRequest,
    CameraResponse,
    CameraStatusResponse,
    AllCamerasStatusResponse
)
from ..utils.logging import get_logger

router = APIRouter(prefix="/cameras", tags=["Cameras"])
logger = get_logger(__name__)

# Path to cameras.json (mounted at /app/cameras.json in Docker)
CAMERAS_JSON_PATH = Path("/app/cameras.json")


@router.get("")
async def list_cameras(
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> List[dict]:
    """
    Get all cameras from PostgreSQL merged with runtime status.
    
    If the database is empty, it seeds it from cameras.json first.
    """
    # Seed database if empty
    await camera_manager.seed_from_json_if_empty()

    # Read from database
    cameras_config = []
    try:
        from ..core.database import db
        cameras_config = await db.fetch_all("SELECT id, name, source, fps, priority, enabled FROM cameras ORDER BY id ASC")
    except Exception as e:
        logger.error(f"Failed to fetch cameras from database: {e}")
        # Fallback to loading from cameras.json
        try:
            if CAMERAS_JSON_PATH.exists():
                with open(CAMERAS_JSON_PATH, "r") as f:
                    data = json.load(f)
                    cameras_config = data.get("cameras", [])
            else:
                logger.warning(f"cameras.json not found at {CAMERAS_JSON_PATH}")
        except (json.JSONDecodeError, OSError) as err:
            logger.error(f"Failed to read cameras.json: {err}")
            return []

    # Get runtime status from camera_manager (local process mode)
    runtime_status = camera_manager.get_all_status()
    runtime_cameras = runtime_status.get("cameras", {})

    # In Docker mode, check Redis for which cameras are actively running
    redis_active_cameras: set = set()
    camera_service_alive = False
    try:
        from ..core.config import get_settings, get_redis_config
        from ..utils.metrics_utils import check_service_liveness
        import redis as redis_lib
        settings = get_settings()
        if settings.is_docker_runtime:
            r_config = get_redis_config()
            r_client = redis_lib.Redis(**r_config)
            camera_service_alive = check_service_liveness(r_client, "camera")
            if camera_service_alive:
                sources = r_client.hgetall("vg:camera:sources")
                for key in sources:
                    cam_id = key.decode("utf-8") if isinstance(key, bytes) else key
                    redis_active_cameras.add(cam_id)
            r_client.close()
    except Exception as e:
        logger.warning(f"Could not check Redis camera liveness: {e}")

    # Merge config with runtime status
    result = []
    for cam in cameras_config:
        cam_id = cam.get("id") or cam.get("camera_id") or ""
        runtime = runtime_cameras.get(cam_id)

        if runtime is not None:
            # Local process manager knows about it
            status = "online" if runtime.get("is_running") else "offline"
            pid = runtime.get("pid")
        elif cam_id in redis_active_cameras:
            # Docker camera container is actively streaming this camera
            status = "online"
            pid = None
        elif camera_service_alive and cam.get("enabled", True):
            # Camera service is alive but this cam isn't in sources — stopped/failed
            status = "offline"
            pid = None
        else:
            status = "offline"
            pid = None

        result.append({
            "id": cam_id,
            "name": cam.get("name", cam_id),
            "source": cam.get("source", cam.get("rtsp_url", "")),
            "fps": cam.get("fps", 5),
            "priority": cam.get("priority", "medium"),
            "enabled": cam.get("enabled", True),
            "motion_threshold": cam.get("motion_threshold", 0.02),
            "status": status,
            "pid": pid,
        })

    return result


@router.post("/register", response_model=CameraResponse)
async def register_camera(
    request: CameraRegisterRequest,
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Register a new camera in the database.
    """
    logger.info(f"Registering camera in database: {request.camera_id}")
    
    try:
        from ..core.database import db
        import time
        await db.execute(
            """
            INSERT INTO cameras (id, name, source, fps, motion_threshold, priority, enabled, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name, source = EXCLUDED.source, fps = EXCLUDED.fps, 
                motion_threshold = EXCLUDED.motion_threshold, priority = EXCLUDED.priority, 
                enabled = EXCLUDED.enabled
            """,
            request.camera_id,
            request.name or request.camera_id,
            request.rtsp_url,
            request.fps or 5,
            request.motion_threshold or 0.02,
            request.priority or "medium",
            request.enabled if request.enabled is not None else True,
            time.time()
        )
        
        # Sync database to cameras.json
        await camera_manager.sync_db_to_json()
        
        # Also register in local memory config of camera_manager for runtime
        camera_manager.register(
            camera_id=request.camera_id,
            rtsp_url=request.rtsp_url,
            fps=request.fps,
            motion_threshold=request.motion_threshold
        )
        
        return CameraResponse(
            success=True,
            message=f"Camera {request.camera_id} registered successfully",
            camera={
                "id": request.camera_id,
                "name": request.name or request.camera_id,
                "source": request.rtsp_url,
                "fps": request.fps or 5,
                "motion_threshold": request.motion_threshold or 0.02,
                "priority": request.priority or "medium",
                "enabled": request.enabled if request.enabled is not None else True
            }
        )
    except Exception as e:
        logger.error(f"Failed to register camera: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {e}"
        )


@router.delete("/{camera_id}", response_model=CameraResponse)
async def unregister_camera(
    camera_id: str = PathParam(..., description="Camera ID to unregister"),
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Unregister/delete a camera from the database.
    """
    logger.info(f"Unregistering camera from database: {camera_id}")
    
    try:
        from ..core.database import db
        await db.execute("DELETE FROM cameras WHERE id = $1", camera_id)
        
        # Sync database to cameras.json
        await camera_manager.sync_db_to_json()
        
        # Also unregister in-memory
        camera_manager.unregister(camera_id)
        
        return CameraResponse(
            success=True,
            message=f"Camera {camera_id} deleted successfully"
        )
    except Exception as e:
        logger.error(f"Failed to delete camera: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {e}"
        )


@router.post("/{camera_id}/start", response_model=CameraResponse)
async def start_camera(
    camera_id: str = PathParam(..., description="Camera ID to start"),
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Start a registered camera (enables it in DB and starts capture process).
    """
    logger.info(f"Starting/Enabling camera: {camera_id}")
    
    # Update enabled status in Postgres
    try:
        from ..core.database import db
        await db.execute("UPDATE cameras SET enabled = TRUE WHERE id = $1", camera_id)
        await camera_manager.sync_db_to_json()
    except Exception as e:
        logger.error(f"Failed to enable camera in DB: {e}")
        
    result = await camera_manager.start_camera(camera_id)
    
    # If starting via local processes is disabled (Docker mode), we return success anyway
    # because we successfully enabled it in the configuration (cameras.json)
    if not result["success"] and "disabled in docker" in result["message"].lower():
        return CameraResponse(
            success=True,
            message=f"Camera {camera_id} enabled for Docker runtime. Restart the camera service to apply.",
            camera={"id": camera_id, "enabled": True}
        )
    
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=result["message"]
        )
    
    return CameraResponse(**result)


@router.post("/{camera_id}/stop", response_model=CameraResponse)
async def stop_camera(
    camera_id: str = PathParam(..., description="Camera ID to stop"),
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Stop a running camera (disables it in DB and stops capture process).
    """
    logger.info(f"Stopping/Disabling camera: {camera_id}")
    
    # Update enabled status in Postgres
    try:
        from ..core.database import db
        await db.execute("UPDATE cameras SET enabled = FALSE WHERE id = $1", camera_id)
        await camera_manager.sync_db_to_json()
    except Exception as e:
        logger.error(f"Failed to disable camera in DB: {e}")
        
    result = await camera_manager.stop_camera(camera_id)
    
    # If stopping via local processes is disabled (Docker mode), we return success anyway
    # because we successfully disabled it in the configuration (cameras.json)
    if not result["success"] and "disabled in docker" in result["message"].lower():
        return CameraResponse(
            success=True,
            message=f"Camera {camera_id} disabled for Docker runtime. Restart the camera service to apply.",
            camera={"id": camera_id, "enabled": False}
        )
    
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=result["message"]
        )
    
    return CameraResponse(**result)


@router.post("/start-all", response_model=CameraResponse)
async def start_all_cameras(
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Start all registered cameras.
    """
    logger.info("Starting all cameras")
    
    result = await camera_manager.start_all()
    
    return CameraResponse(
        success=result["success"],
        message=result["message"],
        camera=None
    )


@router.post("/stop-all", response_model=CameraResponse)
async def stop_all_cameras(
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Stop all running cameras.
    """
    logger.info("Stopping all cameras")
    
    result = await camera_manager.stop_all()
    
    return CameraResponse(
        success=result["success"],
        message=result["message"],
        camera=None
    )


@router.get("/status")
async def get_all_cameras_status(
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> dict:
    """
    Get status of all registered cameras.
    """
    return camera_manager.get_all_status()


@router.get("/{camera_id}/status")
async def get_camera_status(
    camera_id: str = PathParam(..., description="Camera ID"),
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> dict:
    """
    Get status of a specific camera.
    """
    status = camera_manager.get_camera_status(camera_id)
    
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Camera {camera_id} not found"
        )
    
    return status
