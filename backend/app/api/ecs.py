"""
VisionGuard AI - ECS API Routes

Endpoints for Event Classification Service lifecycle control.
POST /ecs/start
POST /ecs/stop
GET  /ecs/status
"""

from fastapi import APIRouter, Depends, HTTPException

from ..services.ecs_manager import get_ecs_manager, ECSManager
from ..models.ecs import ECSStartRequest, ECSControlResponse, ECSStatusResponse
from ..utils.logging import get_logger

router = APIRouter(prefix="/ecs", tags=["ECS"])
logger = get_logger(__name__)


@router.post("/start", response_model=ECSControlResponse)
async def start_ecs(
    request: ECSStartRequest = None,
    ecs_manager: ECSManager = Depends(get_ecs_manager)
) -> ECSControlResponse:
    """
    Start the Event Classification Service.
    
    Starts ECS as a background subprocess. ECS will:
    - Consume AI results from Redis stream
    - Apply classification rules
    - Dispatch alerts and events
    - Manage shared memory cleanup
    
    Optional config overrides can be provided in the request body.
    """
    # Build config override from request
    config_override = {}
    if request:
        if request.correlation_window_ms is not None:
            config_override["correlation_window_ms"] = request.correlation_window_ms
        if request.weapon_threshold is not None:
            config_override["weapon_confidence_threshold"] = request.weapon_threshold
        if request.fire_threshold is not None:
            config_override["fire_confidence_threshold"] = request.fire_threshold
        if request.fall_threshold is not None:
            config_override["fall_confidence_threshold"] = request.fall_threshold
    
    logger.info("Starting ECS via API")
    
    result = await ecs_manager.start(config_override if config_override else None)
    
    if not result["success"]:
        status_code = 409 if "disabled in docker runtime mode" in result["message"].lower() else 500
        # Return 500 on failure but don't crash
        raise HTTPException(
            status_code=status_code,
            detail=result["message"]
        )
    
    return ECSControlResponse(**result)


@router.post("/stop", response_model=ECSControlResponse)
async def stop_ecs(
    ecs_manager: ECSManager = Depends(get_ecs_manager)
) -> ECSControlResponse:
    """
    Stop the Event Classification Service.
    
    Gracefully stops ECS subprocess. Allows current processing to complete
    before termination.
    """
    logger.info("Stopping ECS via API")
    
    result = await ecs_manager.stop()
    
    return ECSControlResponse(**result)


@router.post("/restart", response_model=ECSControlResponse)
async def restart_ecs(
    ecs_manager: ECSManager = Depends(get_ecs_manager)
) -> ECSControlResponse:
    """
    Restart the Event Classification Service.
    
    Stops then starts ECS. Useful for applying configuration changes.
    """
    logger.info("Restarting ECS via API")
    
    result = await ecs_manager.restart()
    
    if not result["success"]:
        status_code = 409 if "disabled in docker runtime mode" in result["message"].lower() else 500
        raise HTTPException(
            status_code=status_code,
            detail=result["message"]
        )
    
    return ECSControlResponse(**result)


@router.get("/status", response_model=ECSStatusResponse)
async def get_ecs_status(
    ecs_manager: ECSManager = Depends(get_ecs_manager)
) -> ECSStatusResponse:
    """
    Get ECS status and statistics.
    
    Returns:
    - Process state (running, stopped, failed, etc.)
    - PID if running
    - Uptime
    - Configuration
    - Last error if any
    """
    status = ecs_manager.get_status()
    
    return ECSStatusResponse(**status)
