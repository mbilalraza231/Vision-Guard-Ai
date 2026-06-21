import json
import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException
import redis as redis_lib

from ..models.zones import ZoneCreate, ZoneUpdate, ZoneResponse, ZoneListResponse
from ..core.database import db
from ..core.config import get_redis_config
from ..utils.logging import get_logger

router = APIRouter(prefix="/api/v1/zones", tags=["Zones"])
logger = get_logger(__name__)


def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record row to a plain dict, casting UUID→str."""
    d = dict(row)
    # UUID columns come back as uuid.UUID — cast to str for Pydantic
    if "id" in d and d["id"] is not None:
        d["id"] = str(d["id"])
    return d


@router.get("", response_model=ZoneListResponse)
async def list_zones():
    try:
        rows = await db.fetch_all("SELECT * FROM zones ORDER BY created_at DESC")
        zones = [ZoneResponse(**_row_to_dict(row)) for row in rows]
        return ZoneListResponse(zones=zones, total=len(zones))
    except Exception as e:
        logger.error(f"Failed to list zones: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("", response_model=ZoneResponse)
async def create_zone(zone: ZoneCreate):
    zone_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    try:
        await db.execute(
            """
            INSERT INTO zones (id, name, active_hours, max_cameras, max_alert_recipients, priority_weapon, priority_fire, priority_fall, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            zone_id, zone.name, zone.active_hours, zone.max_cameras, zone.max_alert_recipients,
            zone.priority_weapon, zone.priority_fire, zone.priority_fall, now
        )
        await _publish_zone_priorities()
        row = await db.fetch_one("SELECT * FROM zones WHERE id = $1", zone_id)
        return ZoneResponse(**_row_to_dict(row))
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
        return ZoneResponse(**_row_to_dict(existing))

    params.append(zone_id)
    query = f"UPDATE zones SET {', '.join(updates)} WHERE id = ${i} RETURNING *"

    try:
        row = await db.fetch_one(query, *params)
        await _publish_zone_priorities()
        return ZoneResponse(**_row_to_dict(row))
    except Exception as e:
        logger.error(f"Failed to update zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str):
    try:
        # Also remove zone_id from cameras
        await db.execute("UPDATE cameras SET zone_id = NULL WHERE zone_id = $1", zone_id)
        await db.execute("DELETE FROM zones WHERE id = $1", zone_id)
        await _publish_zone_priorities()
        return {"status": "success", "message": "Zone deleted"}
    except Exception as e:
        logger.error(f"Failed to delete zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _publish_zone_priorities():
    """
    Rebuild the camera->zone-priority mapping and publish to Redis.
    ECS reads from 'vg:zone_priorities' key and subscribes to 'vg:zone:updates' channel.
    """
    try:
        rows = await db.fetch_all("""
            SELECT
                c.id AS camera_id,
                z.priority_weapon,
                z.priority_fire,
                z.priority_fall
            FROM cameras c
            INNER JOIN zones z ON c.zone_id = z.id::text
            WHERE c.zone_id IS NOT NULL AND c.zone_id != ''
        """)

        mapping = {}
        for row in rows:
            cam_id = row["camera_id"]
            mapping[cam_id] = {
                "weapon": (row["priority_weapon"] or "critical").lower(),
                "fire": (row["priority_fire"] or "high").lower(),
                "fall": (row["priority_fall"] or "medium").lower(),
            }

        r_config = get_redis_config()
        r_client = redis_lib.Redis(**r_config, decode_responses=True)
        payload = json.dumps(mapping)
        r_client.set("vg:zone_priorities", payload)
        r_client.publish("vg:zone:updates", payload)
        r_client.close()

        logger.info(
            f"Published zone priorities to Redis: {len(mapping)} camera(s) with zones")
    except Exception as e:
        logger.warning(f"Failed to publish zone priorities to Redis: {e}")
