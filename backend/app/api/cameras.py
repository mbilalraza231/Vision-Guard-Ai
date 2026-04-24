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
    Get all cameras from cameras.json merged with runtime status.
    
    Returns camera config (name, source, fps, priority, enabled) merged
    with runtime state (running/stopped/unknown, pid).
    """
    # Read cameras.json
    cameras_config = []
    try:
        if CAMERAS_JSON_PATH.exists():
            with open(CAMERAS_JSON_PATH, "r") as f:
                data = json.load(f)
                cameras_config = data.get("cameras", [])
        else:
            logger.warning(f"cameras.json not found at {CAMERAS_JSON_PATH}")
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read cameras.json: {e}")
        return []

    # Get runtime status from camera_manager
    runtime_status = camera_manager.get_all_status()
    runtime_cameras = runtime_status.get("cameras", {})

    # Merge config with runtime status
    result = []
    for cam in cameras_config:
        cam_id = cam.get("id", "")
        runtime = runtime_cameras.get(cam_id)

        if runtime is not None:
            status = "running" if runtime.get("is_running") else "stopped"
            pid = runtime.get("pid")
        else:
            status = "unknown"
            pid = None

        result.append({
            "id": cam_id,
            "name": cam.get("name", cam_id),
            "source": cam.get("source", ""),
            "fps": cam.get("fps", 5),
            "priority": cam.get("priority", "medium"),
            "enabled": cam.get("enabled", True),
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
    Register a new camera.
    
    Camera must be registered before it can be started.
    Registration validates the camera configuration but does not
    connect to the stream.
    """
    logger.info(f"Registering camera: {request.camera_id}")
    
    result = camera_manager.register(
        camera_id=request.camera_id,
        rtsp_url=request.rtsp_url,
        fps=request.fps,
        motion_threshold=request.motion_threshold
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"]
        )
    
    return CameraResponse(**result)


@router.delete("/{camera_id}", response_model=CameraResponse)
async def unregister_camera(
    camera_id: str = PathParam(..., description="Camera ID to unregister"),
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Unregister a camera.
    
    Camera must be stopped before unregistering.
    """
    logger.info(f"Unregistering camera: {camera_id}")
    
    result = camera_manager.unregister(camera_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"]
        )
    
    return CameraResponse(**result)


@router.post("/{camera_id}/start", response_model=CameraResponse)
async def start_camera(
    camera_id: str = PathParam(..., description="Camera ID to start"),
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Start a registered camera.
    
    Begins capturing frames from the RTSP stream and processing
    through the motion detection pipeline.
    """
    logger.info(f"Starting camera: {camera_id}")
    
    result = await camera_manager.start_camera(camera_id)
    
    if not result["success"]:
        status_code = 409 if "disabled in docker runtime mode" in result["message"].lower() else 500
        raise HTTPException(
            status_code=status_code,
            detail=result["message"]
        )
    
    return CameraResponse(**result)


@router.post("/{camera_id}/stop", response_model=CameraResponse)
async def stop_camera(
    camera_id: str = PathParam(..., description="Camera ID to stop"),
    camera_manager: CameraManager = Depends(get_camera_manager)
) -> CameraResponse:
    """
    Stop a running camera.
    
    Gracefully stops the camera capture process.
    """
    logger.info(f"Stopping camera: {camera_id}")
    
    result = await camera_manager.stop_camera(camera_id)
    
    if not result["success"]:
        status_code = 409 if "disabled in docker runtime mode" in result["message"].lower() else 500
        raise HTTPException(
            status_code=status_code,
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
