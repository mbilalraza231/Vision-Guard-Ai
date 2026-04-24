import time
import logging
from typing import Optional, Dict, Any

from .config import AlertConfig
from .repository import AlertRepository

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}


class AlertEvaluator:
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
        self.repo = AlertRepository(self.config)
    
    def is_eligible(self, event: Dict[str, Any]) -> bool:
        severity = event.get("severity", "").lower()
        if severity not in ("critical", "high"):
            return False
        
        confidence = event.get("confidence", 0.0)
        if severity == "critical" and confidence < self.config.min_confidence_critical:
            return False
        if severity == "high" and confidence < self.config.min_confidence_high:
            return False
        
        return True
    
    def _get_dedup_window(self, severity: str) -> int:
        severity = severity.lower()
        if severity == "critical":
            return self.config.dedup_window_critical_sec
        elif severity == "high":
            return self.config.dedup_window_high_sec
        return 0
    
    def is_duplicate(self, event: Dict[str, Any]) -> bool:
        camera_id = event.get("camera_id")
        event_type = event.get("event_type")
        severity = event.get("severity", "").lower()
        confidence = event.get("confidence", 0.0)
        
        dedup_window = self._get_dedup_window(severity)
        if dedup_window == 0:
            return True
        
        since_ts = time.time() - dedup_window
        recent = self.repo.find_recent_alerts(camera_id, event_type, severity, since_ts)
        
        if not recent:
            return False
        
        for alert in recent:
            prev_severity = alert.get("severity", "").lower()
            prev_confidence = alert.get("confidence", 0.0)
            
            if SEVERITY_ORDER.get(severity, 0) > SEVERITY_ORDER.get(prev_severity, 0):
                logger.info(f"Severity escalation: {prev_severity} -> {severity}")
                return False
            
            if confidence - prev_confidence >= self.config.confidence_jump_threshold:
                logger.info(f"Confidence jump: {prev_confidence:.2f} -> {confidence:.2f}")
                return False
        
        return True
    
    def evaluate(self, event: Dict[str, Any]) -> Optional[str]:
        if not self.is_eligible(event):
            logger.debug(f"Event not eligible: severity={event.get('severity')}")
            return None
        
        if self.is_duplicate(event):
            logger.debug(f"Event suppressed (duplicate): {event.get('id')}")
            return None
        
        alert_id = self.repo.create(event["id"], channel="webhook")
        
        if alert_id:
            logger.info(f"Alert created: {alert_id} for event {event['id']}")
        
        return alert_id
