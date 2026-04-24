import json
import logging
from typing import Dict, Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .config import AlertConfig

logger = logging.getLogger(__name__)


class AlertDispatcher:
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
        self.successes = 0
        self.failures = 0
    
    def _build_payload(self, alert: Dict[str, Any]) -> dict:
        return {
            "alert_id": alert.get("id"),
            "event_id": alert.get("event_id"),
            "camera_id": alert.get("camera_id"),
            "event_type": alert.get("event_type"),
            "severity": alert.get("severity"),
            "confidence": alert.get("confidence"),
            "start_ts": alert.get("start_ts"),
            "end_ts": alert.get("end_ts"),
            "created_at": alert.get("created_at"),
            "channel": alert.get("channel")
        }
    
    def dispatch(self, alert: Dict[str, Any]) -> tuple:
        if not self.config.webhook_url:
            logger.warning(f"No webhook URL configured, logging alert: {alert.get('id')}")
            return (True, "logged")
        
        try:
            payload = json.dumps(self._build_payload(alert)).encode("utf-8")
            
            req = Request(
                self.config.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urlopen(req, timeout=self.config.webhook_timeout_sec) as resp:
                if resp.status < 300:
                    self.successes += 1
                    return (True, "sent")
                else:
                    self.failures += 1
                    return (False, f"http_{resp.status}")
                    
        except HTTPError as e:
            self.failures += 1
            if 400 <= e.code < 500:
                return (False, f"terminal_{e.code}")
            return (False, f"http_{e.code}")
            
        except URLError as e:
            self.failures += 1
            return (False, f"network_error")
            
        except Exception as e:
            self.failures += 1
            logger.error(f"Dispatch error: {e}")
            return (False, f"error")
    
    def get_stats(self) -> dict:
        return {
            "successes": self.successes,
            "failures": self.failures,
            "webhook_configured": self.config.webhook_url is not None
        }
