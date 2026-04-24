"""
VisionGuard AI - Detections API Routes

Serves detection images and live bounding box data from Redis stream.

GET  /detections/latest       - List latest detection images metadata
GET  /detections/images/{filename}  - Serve a detection image file
GET  /detections/boxes        - Get recent bounding boxes for live overlay
"""

import os
import glob
import json
import time
from pathlib import Path
from typing import List, Optional

import redis
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..core.config import get_settings

router = APIRouter(prefix="/detections", tags=["Detections"])

DETECTION_DIR = Path("/data/visionguard/detections")
RESULT_STREAM = "vg:ai:results"


def _get_redis():
    """Get Redis connection."""
    settings = get_settings()
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def _parse_filename(filename: str) -> dict:
    """Parse model type, camera ID, and timestamp from detection image filename."""
    parts = filename.replace('.jpg', '').split('_')
    if len(parts) >= 3:
        model = parts[0]
        camera = parts[1]
        try:
            ts_ms = int(parts[-1])
            return {
                "filename": filename,
                "model": model,
                "camera_id": camera,
                "timestamp": ts_ms / 1000,
                "age_seconds": round(time.time() - ts_ms / 1000, 1),
            }
        except (ValueError, OSError):
            pass
    return {
        "filename": filename,
        "model": "unknown",
        "camera_id": "unknown",
        "timestamp": 0,
        "age_seconds": 0,
    }


@router.get("/latest")
async def list_latest_detections(
    model: Optional[str] = Query(None, description="Filter by model type: weapon, fire, fall"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of images to return"),
) -> dict:
    """
    List latest detection images with metadata.
    """
    if not DETECTION_DIR.exists():
        return {"detections": [], "total": 0, "detection_dir_exists": False}

    pattern = "*.jpg"
    if model:
        pattern = f"{model}_*.jpg"

    images = glob.glob(str(DETECTION_DIR / pattern))
    images.sort(key=os.path.getmtime, reverse=True)
    images = images[:limit]

    detections = []
    for img_path in images:
        filename = os.path.basename(img_path)
        info = _parse_filename(filename)
        info["url"] = f"/detections/images/{filename}"
        info["size_bytes"] = os.path.getsize(img_path)
        detections.append(info)

    return {
        "detections": detections,
        "total": len(detections),
        "detection_dir_exists": True,
    }


@router.get("/images/{filename}")
async def serve_detection_image(filename: str):
    """Serve a detection image file."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = DETECTION_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Detection image not found")

    return FileResponse(
        filepath,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/boxes")
async def get_live_boxes(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    limit: int = Query(10, ge=1, le=50, description="Number of recent detections"),
) -> dict:
    """
    Get recent detection bounding boxes from Redis stream for live overlay.

    Returns bounding boxes with model type, confidence, and coordinates
    scaled to 640x640 preprocessed space. Frontend should convert to
    percentage coords: (coord / 640) * 100%.
    """
    try:
        r = _get_redis()
        entries = r.xrevrange(RESULT_STREAM, count=limit * 3)
    except Exception as e:
        return {"boxes": [], "error": str(e)}

    boxes = []
    now = time.time()

    for msg_id, data in entries:
        # Filter by camera if specified
        if camera_id and data.get("camera_id") != camera_id:
            continue

        # Parse timestamp from message ID
        try:
            ts_ms = int(str(msg_id).split("-")[0])
            age_s = (now * 1000 - ts_ms) / 1000
        except Exception:
            age_s = 999

        # Only include recent detections (last 5 seconds)
        if age_s > 5.0:
            continue

        # Parse bbox
        bbox_raw = data.get("bbox")
        bbox = None
        if bbox_raw:
            try:
                bbox = json.loads(bbox_raw)
            except (json.JSONDecodeError, TypeError):
                pass

        conf = float(data.get("confidence", 0))
        model = data.get("model", "unknown")

        if bbox and len(bbox) == 4 and conf > 0:
            boxes.append({
                "model": model,
                "confidence": round(conf, 3),
                "camera_id": data.get("camera_id", ""),
                "bbox": bbox,  # [x1, y1, x2, y2] in 640x640 coords
                "age_seconds": round(age_s, 1),
            })

        if len(boxes) >= limit:
            break

    return {"boxes": boxes, "count": len(boxes)}
