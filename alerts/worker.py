import time
import logging
import threading
from typing import Optional

from .config import AlertConfig
from .repository import AlertRepository
from .dispatcher import AlertDispatcher

logger = logging.getLogger(__name__)


class AlertRetryWorker:
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
        self.repo = AlertRepository(self.config)
        self.dispatcher = AlertDispatcher(self.config)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.processed = 0
        self.sent = 0
        self.failed = 0
    
    def _get_backoff(self, attempts: int) -> int:
        schedule = self.config.backoff_schedule
        if attempts >= len(schedule):
            return schedule[-1]
        return schedule[attempts]
    
    def _is_expired(self, alert: dict) -> bool:
        created_at = alert.get("created_at", 0)
        expire_ts = created_at + (self.config.expire_after_hours * 3600)
        return time.time() > expire_ts
    
    def _should_retry(self, alert: dict) -> bool:
        attempts = alert.get("attempts", 0)
        if attempts >= self.config.max_attempts:
            return False
        
        if self._is_expired(alert):
            return False
        
        last_attempt = alert.get("last_attempt_ts")
        if last_attempt is None:
            return True
        
        backoff = self._get_backoff(attempts)
        return time.time() >= (last_attempt + backoff)
    
    def process_one(self, alert: dict) -> bool:
        self.repo.increment_attempts(alert["id"])
        
        success, reason = self.dispatcher.dispatch(alert)
        
        if success:
            self.repo.update_status(alert["id"], "sent")
            self.sent += 1
            logger.info(f"Alert sent: {alert['id']}")
            return True
        else:
            if reason.startswith("terminal"):
                self.repo.update_status(alert["id"], "failed")
                logger.warning(f"Alert failed (terminal): {alert['id']} - {reason}")
            else:
                self.repo.update_status(alert["id"], "failed")
                logger.warning(f"Alert failed (retriable): {alert['id']} - {reason}")
            self.failed += 1
            return False
    
    def run_once(self) -> int:
        pending = self.repo.get_pending_alerts(self.config.max_attempts)
        processed = 0
        
        for alert in pending:
            if not self._should_retry(alert):
                continue
            
            self.process_one(alert)
            processed += 1
            self.processed += 1
        
        return processed
    
    def start(self, poll_interval: float = 5.0):
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            args=(poll_interval,),
            name="AlertRetryWorker",
            daemon=True
        )
        self._thread.start()
        logger.info("AlertRetryWorker started")
    
    def _worker_loop(self, poll_interval: float):
        while self._running:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Worker error: {e}")
            
            time.sleep(poll_interval)
    
    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("AlertRetryWorker stopped")
    
    def get_stats(self) -> dict:
        return {
            "processed": self.processed,
            "sent": self.sent,
            "failed": self.failed,
            "running": self._running,
            "dispatcher": self.dispatcher.get_stats()
        }
