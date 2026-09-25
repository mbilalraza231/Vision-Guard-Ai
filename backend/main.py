"""
VisionGuard AI - FastAPI Backend Supervisor

The control plane and orchestrator for the VisionGuard AI system.

This backend:
- Controls ECS lifecycle (start/stop/monitor)
- Manages camera pipelines
- Exposes health, status, and metrics APIs
- Provides event and alert read APIs

This backend does NOT:
- Perform AI inference
- Perform event classification
- Consume Redis streams directly
- Manage shared memory

Usage:
    python main.py
    
    Or with uvicorn:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import sys
import os
import time

# Add project root and backend to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_ROOT)

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from app.core.config import get_settings
from app.core.lifecycle import lifespan
from app.api import system, ecs, cameras, events, detections, stream, alerts, zones
from app.api.settings import router as settings_router
from app.utils.logging import setup_logging, get_logger

# Initialize logging early
settings = get_settings()
setup_logging(level=settings.log_level, format_type="text")
logger = get_logger(__name__)

# Prometheus Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests processed by endpoint and status code",
    ["method", "handler", "status"]
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "handler"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in ["/metrics", "/health"]:
            return await call_next(request)
            
        start_time = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration = time.time() - start_time
            # Determine handler label safely
            handler = path
            HTTP_REQUESTS_TOTAL.labels(method=request.method, handler=handler, status=str(status_code)).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, handler=handler).observe(duration)


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
    
    # Add Prometheus metrics middleware
    app.add_middleware(PrometheusMiddleware)
    
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
    app.include_router(stream.router)
    app.include_router(alerts.router)
    app.include_router(settings_router)
    app.include_router(zones.router)

    # Expose Prometheus /metrics
    @app.get("/metrics", tags=["System"], include_in_schema=False)
    def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    
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
