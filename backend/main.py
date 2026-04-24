"""
VisionGuard AI - FastAPI Backend Supervisor

The control plane and orchestrator for the VisionGuard AI system.

This backend:
✅ Controls ECS lifecycle (start/stop/monitor)
✅ Manages camera pipelines
✅ Exposes health, status, and metrics APIs
✅ Provides event and alert read APIs

This backend does NOT:
❌ Perform AI inference
❌ Perform event classification
❌ Consume Redis streams directly
❌ Manage shared memory

Usage:
    python main.py
    
    Or with uvicorn:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import sys
import os

# Add project root and backend to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.lifecycle import lifespan
from app.api import system, ecs, cameras, events, detections
from app.utils.logging import setup_logging, get_logger

# Initialize logging early
settings = get_settings()
setup_logging(level=settings.log_level, format_type="text")
logger = get_logger(__name__)


# ==================== APPLICATION FACTORY ====================

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI instance
    """
    app = FastAPI(
        title=settings.app_name,
        description="""
## VisionGuard AI Backend Supervisor

Control plane for the VisionGuard AI surveillance system.

### Capabilities
- **ECS Control**: Start, stop, and monitor the Event Classification Service
- **Camera Management**: Register, start, stop, and monitor camera pipelines
- **System Status**: Health checks, metrics, and component status
- **Events & Alerts**: Read classified events and alerts

### Architecture
This backend supervises external services - it does NOT perform:
- AI inference (handled by AI Workers)
- Event classification (handled by ECS)
- Frame storage (handled by Camera Capture)
        """,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(system.router)
    app.include_router(ecs.router)
    app.include_router(cameras.router)
    app.include_router(events.router)
    app.include_router(detections.router)
    
    return app


# Create application instance
app = create_app()


# ==================== ROOT ENDPOINT ====================

@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint - API information.
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs",
        "health": "/health",
        "status": "/status"
    }


# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
        access_log=settings.is_development
    )
