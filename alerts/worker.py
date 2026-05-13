import time
import logging
import asyncio
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
        self._task: Optional[asyncio.Task] = None
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
    
    async def process_one(self, alert: dict) -> bool:
        await self.repo.increment_attempts(alert["id"])
        
        # Dispatcher is synchronous (urllib), so we run it in a thread 
        # to avoid blocking the event loop.
        success, reason = await asyncio.to_thread(self.dispatcher.dispatch, alert)
        
        if success:
            await self.repo.update_status(alert["id"], "sent")
            self.sent += 1
            logger.info(f"Alert sent: {alert['id']}")
            return True
        else:
            await self.repo.update_status(alert["id"], "failed")
            if reason.startswith("terminal"):
                logger.warning(f"Alert failed (terminal): {alert['id']} - {reason}")
            else:
                logger.warning(f"Alert failed (retriable): {alert['id']} - {reason}")
            self.failed += 1
            return False
    
    async def run_once(self) -> int:
        pending = await self.repo.get_pending_alerts(self.config.max_attempts)
        processed = 0
        
        for alert in pending:
            if not self._should_retry(alert):
                continue
            
            await self.process_one(alert)
            processed += 1
            self.processed += 1
        
        return processed
    
    def start(self, poll_interval: float = 5.0):
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._worker_loop(poll_interval))
        logger.info("AlertRetryWorker task started")
    
    async def _worker_loop(self, poll_interval: float):
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Worker error: {e}")
            
            await asyncio.sleep(poll_interval)
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AlertRetryWorker stopped")
    
    def get_stats(self) -> dict:
        return {
            "processed": self.processed,
            "sent": self.sent,
            "failed": self.failed,
            "running": self._running,
            "dispatcher": self.dispatcher.get_stats()
        }
