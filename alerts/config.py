import os
from dataclasses import dataclass


@dataclass
class AlertConfig:
    db_path: str = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # Twilio (SMS/WhatsApp)
    twilio_sid: str = None
    twilio_auth_token: str = None
    twilio_from: str = None
    
    # Gmail (SMTP)
    gmail_user: str = None
    gmail_password: str = None  # App-specific password
    
    # Cloudinary (for predictable URLs)
    cloudinary_cloud_name: str = None
    
    # Alert Logic
    min_confidence_critical: float = 0.85
    min_confidence_high: float = 0.75
    max_attempts: int = 5
    backoff_schedule: tuple = (0, 30, 120, 600, 1800)
    expire_after_hours: int = 24
    # Deduplication windows (seconds). 0 = no dedup for that severity.
    dedup_window_critical_sec: int = 300   # 5 min
    dedup_window_high_sec: int = 120       # 2 min
    confidence_jump_threshold: float = 0.15
    
    def __post_init__(self):
        if self.db_path is None:
            self.db_path = os.getenv("VG_DB_PATH", "/data/visionguard/events.db")
        
        # Redis
        self.redis_host = os.getenv("VG_REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("VG_REDIS_PORT", 6379))
            
        # Twilio
        self.twilio_sid = os.getenv("VG_TWILIO_SID")
        self.twilio_auth_token = os.getenv("VG_TWILIO_AUTH_TOKEN")
        self.twilio_from = os.getenv("VG_TWILIO_FROM")
        
        # Gmail
        self.gmail_user = os.getenv("VG_GMAIL_USER")
        self.gmail_password = os.getenv("VG_GMAIL_PASSWORD")
        
        # Cloudinary
        self.cloudinary_cloud_name = os.getenv("VG_CLOUDINARY_CLOUD_NAME")
