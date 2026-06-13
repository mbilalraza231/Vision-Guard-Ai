import uuid
import time
from typing import List
from fastapi import APIRouter, HTTPException

from ..models.zones import ZoneCreate, ZoneUpdate, ZoneResponse, ZoneListResponse
from ..core.database import db
from ..utils.logging import get_logger

router = APIRouter(prefix="/api/v1/zones", tags=["Zones"])
logger = get_logger(__name__)

@router.get("", response_model=ZoneListResponse)
async def list_zones():
    try:
        rows = await db.fetch_all("SELECT * FROM zones ORDER BY created_at DESC")
        zones = [ZoneResponse(**row) for row in rows]
        return ZoneListResponse(zones=zones, total=len(zones))
    except Exception as e:
        logger.error(f"Failed to list zones: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("", response_model=ZoneResponse)
async def create_zone(zone: ZoneCreate):
    zone_id = str(uuid.uuid4())
    now = time.time()
    try:
        await db.execute(
            """
            INSERT INTO zones (id, name, active_hours, max_cameras, max_alert_recipients, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            zone_id, zone.name, zone.active_hours, zone.max_cameras, zone.max_alert_recipients, now
        )
        return ZoneResponse(id=zone_id, created_at=now, **zone.model_dump())
    except Exception as e:
        logger.error(f"Failed to create zone: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/{zone_id}", response_model=ZoneResponse)
async def update_zone(zone_id: str, patch: ZoneUpdate):
    existing = await db.fetch_one("SELECT * FROM zones WHERE id = $1", zone_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    updates = []
    params = []
    i = 1
    for field, value in patch.model_dump(exclude_unset=True).items():
        updates.append(f"{field} = ${i}")
        params.append(value)
        i += 1
    
    if not updates:
        return ZoneResponse(**existing)
    
    params.append(zone_id)
    query = f"UPDATE zones SET {', '.join(updates)} WHERE id = ${i} RETURNING *"
    
    try:
        row = await db.fetch_one(query, *params)
        return ZoneResponse(**row)
    except Exception as e:
        logger.error(f"Failed to update zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{zone_id}")
async def delete_zone(zone_id: str):
    try:
        # Also remove zone_id from cameras
        await db.execute("UPDATE cameras SET zone_id = NULL WHERE zone_id = $1", zone_id)
        await db.execute("DELETE FROM zones WHERE id = $1", zone_id)
        return {"status": "success", "message": "Zone deleted"}
    except Exception as e:
        logger.error(f"Failed to delete zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
