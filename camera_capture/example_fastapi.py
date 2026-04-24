"""
Example FastAPI Integration for VisionGuard AI Camera Capture Module

This demonstrates how to integrate the camera_capture module with FastAPI.
"""

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import json
from pathlib import Path

# Import camera capture module
from camera_capture import (
    start_cameras,
    stop_cameras,
    get_status,
    restart_camera,
    CaptureConfig
)


# Global process manager
manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    Handles startup and shutdown of camera processes.
    """
    global manager
    
    # Startup: Load config and start cameras
    print("Starting camera capture module...")
    
    # Load configuration from file
    config_path = Path("camera_config.json")
    
    if config_path.exists():
        with open(config_path) as f:
            config_dict = json.load(f)
        config = CaptureConfig(**config_dict)
    else:
        # Default configuration for testing
        from camera_capture import CameraConfig
        
        config = CaptureConfig(
            cameras=[
                CameraConfig(
                    camera_id="cam_001",
                    rtsp_url="rtsp://192.168.1.100:554/stream",
                    fps=5,
                    motion_threshold=0.02
                )
            ]
        )
    
    # Start all cameras
    manager = start_cameras(config)
    print(f"Started {len(config.cameras)} camera(s)")
    
    yield
    
    # Shutdown: Stop all cameras
    print("Stopping camera capture module...")
    if manager:
        stop_cameras(manager, timeout=10.0)
    print("Camera capture module stopped")


# Create FastAPI app
app = FastAPI(
    title="VisionGuard AI - Camera Capture API",
    description="Control plane for camera capture processes",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "VisionGuard AI - Camera Capture",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/cameras/status")
async def cameras_status():
    """
    Get status of all camera processes.
    
    Returns:
        Dictionary mapping camera_id to status info
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Camera manager not initialized")
    
    return get_status(manager)


@app.get("/cameras/{camera_id}/status")
async def camera_status(camera_id: str):
    """
    Get status of a specific camera.
    
    Args:
        camera_id: Camera identifier
        
    Returns:
        Status info for the camera
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Camera manager not initialized")
    
    all_status = get_status(manager)
    
    if camera_id not in all_status:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    return all_status[camera_id]


@app.post("/cameras/{camera_id}/restart")
async def restart_camera_endpoint(camera_id: str):
    """
    Restart a specific camera process.
    
    Args:
        camera_id: Camera identifier
        
    Returns:
        Success status
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Camera manager not initialized")
    
    # Check if camera exists
    all_status = get_status(manager)
    if camera_id not in all_status:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    # Restart camera
    success = restart_camera(manager, camera_id)
    
    if success:
        return {
            "success": True,
            "message": f"Camera {camera_id} restarted successfully"
        }
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restart camera {camera_id}"
        )


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status of the service
    """
    if not manager:
        return {
            "status": "unhealthy",
            "reason": "Camera manager not initialized"
        }
    
    # Check if any cameras are alive
    all_status = get_status(manager)
    alive_count = sum(1 for info in all_status.values() if info["is_alive"])
    total_count = len(all_status)
    
    if alive_count == 0:
        return {
            "status": "unhealthy",
            "reason": "No cameras are alive",
            "cameras": {
                "total": total_count,
                "alive": alive_count
            }
        }
    
    return {
        "status": "healthy",
        "cameras": {
            "total": total_count,
            "alive": alive_count
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    # Run the FastAPI app
    uvicorn.run(
        "example_fastapi:app",
        host="0.0.0.0",
        port=8000,
        reload=False  # Don't use reload with multiprocessing
    )
