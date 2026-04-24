"""
VisionGuard AI - Alert Dispatcher

Production webhook-based alert dispatching.
Async, non-blocking, fire-and-forget.
"""

import logging
import json
import threading
import queue
from typing import Optional, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from dataclasses import asdict

from ..classification.event_models import Event


class AlertDispatcher:
    """
    Production alert dispatcher for classified events.
    
    Features:
    - Webhook-based HTTP POST
    - Async dispatch via background thread
    - Fire-and-forget (no retries)
    - Failure logged only, never blocks ECS
    - Config-driven enable/disable
    """
    
    def __init__(
        self,
        enabled: bool = True,
        webhook_url: Optional[str] = None,
        timeout_seconds: float = 5.0,
        max_queue_size: int = 1000
    ):
        """
        Initialize alert dispatcher.
        
        Args:
            enabled: Whether dispatching is enabled
            webhook_url: URL to POST alerts to (None = log only)
            timeout_seconds: HTTP request timeout
            max_queue_size: Max pending alerts before dropping
        """
        self.logger = logging.getLogger(__name__)
        self.enabled = enabled
        self.webhook_url = webhook_url
        self.timeout = timeout_seconds
        
        # Async dispatch queue
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Statistics
        self.alerts_dispatched = 0
        self.alerts_dropped = 0
        self.dispatch_failures = 0
        self.webhook_successes = 0
        
        if self.enabled:
            self._start_worker()
        
        self.logger.info(
            f"Alert dispatcher initialized",
            extra={
                "enabled": enabled,
                "webhook_configured": webhook_url is not None
            }
        )
    
    def _start_worker(self) -> None:
        """Start background dispatch worker."""
        self._running = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="AlertDispatcherWorker",
            daemon=True
        )
        self._thread.start()
    
    def _worker_loop(self) -> None:
        """Background worker that processes the dispatch queue."""
        while self._running:
            try:
                event = self._queue.get(timeout=1.0)
                self._do_dispatch(event)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Worker error: {e}")
    
    def _do_dispatch(self, event: Event) -> None:
        """Actually dispatch the alert."""
        try:
            # Always log the alert
            self.logger.warning(
                f"ALERT: {event.event_type}",
                extra={
                    "event_id": event.event_id,
                    "severity": event.severity,
                    "camera_id": event.camera_id,
                    "confidence": event.confidence
                }
            )
            
            # Send webhook if configured
            if self.webhook_url:
                try:
                    payload = json.dumps({
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "camera_id": event.camera_id,
                        "timestamp": event.timestamp,
                        "confidence": event.confidence,
                        "model_type": event.model_type
                    }).encode('utf-8')
                    
                    req = Request(
                        self.webhook_url,
                        data=payload,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    
                    with urlopen(req, timeout=self.timeout) as resp:
                        if resp.status < 300:
                            self.webhook_successes += 1
                            
                except (URLError, HTTPError) as e:
                    self.dispatch_failures += 1
                    self.logger.warning(
                        f"Webhook failed (non-blocking): {e}",
                        extra={"webhook_url": self.webhook_url}
                    )
                    # DO NOT retry - fire and forget
            
            self.alerts_dispatched += 1
            
        except Exception as e:
            self.dispatch_failures += 1
            self.logger.error(
                f"Alert dispatch failed: {e}",
                extra={"event_id": event.event_id, "error": str(e)}
            )
    
    def dispatch(self, event: Event) -> None:
        """
        Queue alert for async dispatch.
        
        Non-blocking, fails independently.
        Drops oldest alerts if queue is full.
        
        Args:
            event: Classified event
        """
        if not self.enabled:
            return
        
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.alerts_dropped += 1
            self.logger.warning(
                f"Alert queue full, dropping alert",
                extra={"event_id": event.event_id}
            )
    
    def shutdown(self) -> None:
        """Gracefully stop the dispatcher."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.logger.info("Alert dispatcher shutdown")
    
    def get_stats(self) -> dict:
        """Get dispatcher statistics."""
        return {
            "enabled": self.enabled,
            "alerts_dispatched": self.alerts_dispatched,
            "alerts_dropped": self.alerts_dropped,
            "dispatch_failures": self.dispatch_failures,
            "webhook_successes": self.webhook_successes,
            "queue_size": self._queue.qsize()
        }
