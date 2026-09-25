"""
VisionGuard AI - Root Entry Point
Delegates to backend.main for FastAPI application.
"""

import sys
import os

# Ensure project root and backend folder are in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.main import app, create_app

if __name__ == "__main__":
    import uvicorn
    from backend.app.core.config import get_settings
    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
        access_log=settings.is_development
    )
