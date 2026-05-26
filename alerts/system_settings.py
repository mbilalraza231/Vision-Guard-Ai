from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class SystemSettings:
    # General
    siteName: str = "VisionGuard AI"
    timezone: str = "UTC"
    language: str = "en"
    # Alerts
    emailNotifications: bool = False
    smsNotifications: bool = False
    pushNotifications: bool = False
    alertThreshold: str = "low"
    # Storage
    retentionDays: int = 30
    autoDelete: bool = False
    maxStorage: int = 50
    # Models
    detectionModel: str = "yolo-edge-v2"
    confidenceThreshold: float = 0.7
    processingMode: str = "realtime"
    # Privacy
    maskFaces: bool = False
    anonymizeData: bool = False
    gdprCompliant: bool = False
    # Notification credentials (nested)
    notifications: Dict[str, Any] = field(
        default_factory=lambda: {
            "twilio": {"sid": "", "token": "", "from": ""},
            "gmail": {"server": "smtp.gmail.com", "user": "", "pass": ""},
        }
    )
