"""
VisionGuard AI - Frontend Publisher

Production async queue for frontend consumers.
Non-blocking, backpressure-safe.
"""

import logging
import threading
import queue
from typing import Optional, Dict, Any, List, Callable
from collections import deque
from dataclasses import asdict

from ..classification.event_models import Event


class FrontendPublisher:
    """
    Production frontend publisher for classified events.
    
    Features:
    - Thread-safe bounded queue
    - Oldest events dropped on overflow (backpressure)
    - Backend API reads queue
    - Callbacks for WebSocket/SSE integration
    - Config-driven enable/disable
    """
    
    def __init__(
        self,
        enabled: bool = True,
        max_queue_size: int = 1000,
        max_subscribers: int = 10
    ):
        """
        Initialize frontend publisher.
        
        Args:
            enabled: Whether publishing is enabled
            max_queue_size: Max events in queue before dropping oldest
            max_subscribers: Max simultaneous subscribers
        """
        self.logger = logging.getLogger(__name__)
        self.enabled = enabled
        self.max_queue_size = max_queue_size
        
        # Thread-safe event buffer (ring buffer behavior)
        self._events: deque = deque(maxlen=max_queue_size)
        self._lock = threading.RLock()
        
        # Subscriber callbacks for real-time push
        self._subscribers: Dict[str, Callable[[Dict], None]] = {}
        self._max_subscribers = max_subscribers
        
        # Statistics
        self.events_published = 0
        self.events_dropped = 0
        self.publish_failures = 0
        self.subscriber_pushes = 0
        
        self.logger.info(
            f"Frontend publisher initialized",
            extra={"enabled": enabled, "max_queue_size": max_queue_size}
        )
    
    def publish(self, event: Event) -> None:
        """
        Publish event to frontend queue.
        
        Non-blocking, fails independently.
        Drops oldest events if queue is full.
        
        Args:
            event: Classified event
        """
        if not self.enabled:
            return
        
        try:
            event_dict = {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "severity": event.severity,
                "camera_id": event.camera_id,
                "timestamp": event.timestamp,
                "confidence": event.confidence,
                "model_type": event.model_type
            }
            
            with self._lock:
                # Check if we're at capacity (will auto-drop oldest)
                if len(self._events) >= self.max_queue_size:
                    self.events_dropped += 1
                
                self._events.append(event_dict)
                self.events_published += 1
            
            # Push to subscribers (non-blocking)
            self._notify_subscribers(event_dict)
            
            self.logger.debug(
                f"FRONTEND PUBLISH: {event.event_type}",
                extra={
                    "event_id": event.event_id,
                    "severity": event.severity,
                    "camera_id": event.camera_id
                }
            )
            
        except Exception as e:
            self.publish_failures += 1
            
            self.logger.error(
                f"Frontend publish failed: {e}",
                extra={"event_id": event.event_id, "error": str(e)}
            )
    
    def _notify_subscribers(self, event_dict: Dict[str, Any]) -> None:
        """Notify all subscribers of new event."""
        failed_subs = []
        
        for sub_id, callback in self._subscribers.items():
            try:
                callback(event_dict)
                self.subscriber_pushes += 1
            except Exception as e:
                self.logger.warning(f"Subscriber {sub_id} failed: {e}")
                failed_subs.append(sub_id)
        
        # Remove failed subscribers
        for sub_id in failed_subs:
            self.unsubscribe(sub_id)
    
    def subscribe(self, subscriber_id: str, callback: Callable[[Dict], None]) -> bool:
        """
        Register a callback for real-time events.
        
        Args:
            subscriber_id: Unique subscriber identifier
            callback: Function to call with each event
            
        Returns:
            True if subscribed, False if at capacity
        """
        if len(self._subscribers) >= self._max_subscribers:
            self.logger.warning(f"Max subscribers reached, rejecting {subscriber_id}")
            return False
        
        self._subscribers[subscriber_id] = callback
        self.logger.info(f"Subscriber added: {subscriber_id}")
        return True
    
    def unsubscribe(self, subscriber_id: str) -> bool:
        """Remove a subscriber."""
        if subscriber_id in self._subscribers:
            del self._subscribers[subscriber_id]
            self.logger.info(f"Subscriber removed: {subscriber_id}")
            return True
        return False
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent events from the queue.
        
        Used by backend API for polling.
        
        Args:
            limit: Max number of events to return
            
        Returns:
            List of event dictionaries (newest first)
        """
        with self._lock:
            events = list(self._events)
            events.reverse()  # Newest first
            return events[:limit]
    
    def clear_events(self) -> int:
        """Clear the event queue. Returns number cleared."""
        with self._lock:
            count = len(self._events)
            self._events.clear()
            return count
    
    def shutdown(self) -> None:
        """Gracefully shutdown, clearing subscriptions."""
        self._subscribers.clear()
        self.logger.info("Frontend publisher shutdown")
    
    def get_stats(self) -> dict:
        """Get publisher statistics."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "events_published": self.events_published,
                "events_dropped": self.events_dropped,
                "publish_failures": self.publish_failures,
                "subscriber_pushes": self.subscriber_pushes,
                "queue_size": len(self._events),
                "subscriber_count": len(self._subscribers)
            }
