import os
from dataclasses import dataclass


@dataclass
class AlertConfig:
    db_path: str = None
    min_confidence_critical: float = 0.85
    min_confidence_high: float = 0.75
    dedup_window_critical_sec: int = 60
    dedup_window_high_sec: int = 300
    confidence_jump_threshold: float = 0.15
    max_attempts: int = 5
    backoff_schedule: tuple = (0, 30, 120, 600, 1800)
    expire_after_hours: int = 24
    webhook_url: str = None
    webhook_timeout_sec: float = 5.0
    
    def __post_init__(self):
        if self.db_path is None:
            self.db_path = os.getenv("VG_DB_PATH", "/data/visionguard/events.db")
        if self.webhook_url is None:
            self.webhook_url = os.getenv("VG_ALERT_WEBHOOK_URL")
