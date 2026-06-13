from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class AlertContactBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: bool = True
    email_alert: bool = True
    min_severity: str = "medium"
    is_active: bool = True
    zone_ids: str = '[]'

class AlertContactCreate(AlertContactBase):
    pass

class AlertContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[bool] = None
    email_alert: Optional[bool] = None
    min_severity: Optional[str] = None
    is_active: Optional[bool] = None
    zone_ids: Optional[str] = None

class AlertContact(AlertContactBase):
    id: str
    created_at: float

    class Config:
        from_attributes = True

class AlertContactListResponse(BaseModel):
    contacts: List[AlertContact]
    total: int
