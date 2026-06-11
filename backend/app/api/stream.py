"""
VisionGuard AI - Global SSE Stream API Routes

Provides a single multiplexed Server-Sent Events stream for the entire dashboard
to eliminate HTTP short-polling.
"""

import json
import asyncio
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from .system import system_status, system_metrics
from .events import get_event_stats
from ..services.ecs_manager import get_ecs_manager, ECSManager
from ..services.camera_manager import get_camera_manager, CameraManager
from ..services.db_reader import get_db_reader
from ..core.config import get_settings, Settings
from .detections import get_live_boxes
from alerts.repository import AlertRepository

router = APIRouter(prefix="/stream", tags=["Stream"])

async def global_event_generator(
    request: Request,
    ecs_manager: ECSManager,
    camera_manager: CameraManager,
    settings: Settings
):
    db_reader = get_db_reader()
    
    while True:
        if await request.is_disconnected():
            break
            
        try:
            # 1. System Status & Metrics
            status_data = await system_status(ecs_manager, camera_manager, settings)
            metrics_data = await system_metrics(ecs_manager, camera_manager, settings)
            
            # 2. Camera List
            from .cameras import list_cameras
            cameras_data = await list_cameras(camera_manager)
            
            # 3. Events Stats
            stats_data = await db_reader.get_stats()
            
            # 4. Recent Events
            recent_events_data = await db_reader.list_events(limit=5)
            
            # 5. Live Bounding Boxes
            boxes_data = await get_live_boxes(limit=50)

            # 6. Alert History (Used by AlertContacts for count monitoring)
            # limit=1: Only fetch the single newest alert. SSE uses it for Level 3 cache injection.
            # The actual paginated history is loaded via HTTP GET in AlertContacts.tsx.
            alert_repo = AlertRepository()
            alerts_data = await alert_repo.list_alerts(limit=1)

            # Combine everything
            payload = {
                "status": status_data.dict(),
                "metrics": metrics_data.dict(),
                "cameras": cameras_data,
                "stats": stats_data,
                "recentEvents": recent_events_data,
                "boxes": boxes_data,
                "alerts": alerts_data
            }
            
            yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
        # Push every 1.5 seconds to match the previous bounding box polling rate
        await asyncio.sleep(1.5)

@router.get("/global")
async def global_stream(
    request: Request,
    ecs_manager: ECSManager = Depends(get_ecs_manager),
    camera_manager: CameraManager = Depends(get_camera_manager),
    settings: Settings = Depends(get_settings)
):
    """
    Unified Server-Sent Events (SSE) endpoint for real-time dashboard data.
    """
    return StreamingResponse(
        global_event_generator(request, ecs_manager, camera_manager, settings),
        media_type="text/event-stream"
    )
