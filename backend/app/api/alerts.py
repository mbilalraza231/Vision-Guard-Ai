import uuid
import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from ..models.alerts import (
    AlertContact, AlertContactCreate, AlertContactUpdate, AlertContactListResponse
)
from ..core.database import db
from ..utils.logging import get_logger

router = APIRouter(prefix="/api/v1/alert-recipients", tags=["Alert Recipients"])
logger = get_logger(__name__)

@router.get("", response_model=AlertContactListResponse)
async def list_contacts():
    """List all alert contacts."""
    try:
        rows = await db.fetch_all("SELECT * FROM alert_contacts ORDER BY created_at DESC")
        contacts = [AlertContact(**row) for row in rows]
        return AlertContactListResponse(contacts=contacts, total=len(contacts))
    except Exception as e:
        logger.error(f"Failed to list contacts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("", response_model=AlertContact)
async def create_contact(contact: AlertContactCreate):
    """Create a new alert contact."""
    contact_id = str(uuid.uuid4())
    now = time.time()
    try:
        await db.execute(
            """
            INSERT INTO alert_contacts (id, name, phone, email, whatsapp, email_alert, min_severity, is_active, zone_ids, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            contact_id, contact.name, contact.phone, contact.email, 
            contact.whatsapp, contact.email_alert, contact.min_severity, 
            contact.is_active, contact.zone_ids, now
        )
        return AlertContact(id=contact_id, created_at=now, **contact.model_dump())
    except Exception as e:
        logger.error(f"Failed to create contact: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/{contact_id}", response_model=AlertContact)
async def update_contact(contact_id: str, patch: AlertContactUpdate):
    """Update an existing alert contact."""
    # Check if exists
    existing = await db.fetch_one("SELECT * FROM alert_contacts WHERE id = $1", contact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    # Build update query
    updates = []
    params = []
    i = 1
    for field, value in patch.model_dump(exclude_unset=True).items():
        updates.append(f"{field} = ${i}")
        params.append(value)
        i += 1
    
    if not updates:
        return AlertContact(**existing)
    
    params.append(contact_id)
    query = f"UPDATE alert_contacts SET {', '.join(updates)} WHERE id = ${i} RETURNING *"
    
    try:
        row = await db.fetch_one(query, *params)
        return AlertContact(**row)
    except Exception as e:
        logger.error(f"Failed to update contact {contact_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{contact_id}")
async def delete_contact(contact_id: str):
    """Delete an alert contact."""
    try:
        await db.execute("DELETE FROM alert_contacts WHERE id = $1", contact_id)
        return {"status": "success", "message": "Contact deleted"}
    except Exception as e:
        logger.error(f"Failed to delete contact {contact_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
