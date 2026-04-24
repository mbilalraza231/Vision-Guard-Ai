"""
VisionGuard AI - Database Writer

Production SQLite-based event persistence.
WRITE-ONLY access from ECS.

Derives:
- start_ts = end_ts - (correlation_age_ms / 1000.0)
- end_ts = event.timestamp

No modification to Event dataclass.
"""

import logging
import sqlite3
import threading
import queue
import time
import os
from typing import Optional, List

from ..classification.event_models import Event
from db.init_db import init_database, get_db_path


class DatabaseWriter:
    """
    Production database writer for classified events.
    
    Features:
    - SQLite with WAL mode
    - Async writes via background thread
    - Batched inserts for efficiency
    - Failure never blocks ECS
    - Derives start_ts/end_ts from correlation_age_ms
    
    WRITE-ONLY: ECS is the sole writer.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        db_path: str = None,
        batch_size: int = 10,
        flush_interval_sec: float = 5.0,
        max_queue_size: int = 5000,
        model_version: str = None
    ):
        """
        Initialize database writer.
        
        Args:
            enabled: Whether writing is enabled
            db_path: Path to SQLite database file
            batch_size: Number of events to batch before writing
            flush_interval_sec: Max time before forcing a write
            max_queue_size: Max pending events before dropping
            model_version: Model version string for DB records
        """
        self.logger = logging.getLogger(__name__)
        self.enabled = enabled
        self.db_path = db_path or get_db_path()
        self.batch_size = batch_size
        self.flush_interval = flush_interval_sec
        self.model_version = model_version or os.getenv("VG_MODEL_VERSION", "1.0.0")
        
        # Write queue
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Statistics
        self.events_written = 0
        self.events_dropped = 0
        self.write_failures = 0
        self.batches_written = 0
        
        if self.enabled:
            self._init_db()
            self._start_worker()
        
        self.logger.info(
            f"Database writer initialized",
            extra={"enabled": enabled, "db_path": self.db_path}
        )
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        try:
            init_database(self.db_path)
            self.logger.info(f"Database initialized: {self.db_path}")
        except Exception as e:
            self.logger.error(f"Database init failed: {e}")
    
    def _start_worker(self) -> None:
        """Start background write worker."""
        self._running = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="DatabaseWriterWorker",
            daemon=True
        )
        self._thread.start()
    
    def _worker_loop(self) -> None:
        """Background worker that batches and writes events."""
        batch: List[Event] = []
        last_flush = time.time()
        
        while self._running:
            try:
                # Get event with timeout
                try:
                    event = self._queue.get(timeout=0.5)
                    batch.append(event)
                    self._queue.task_done()
                except queue.Empty:
                    pass
                
                # Check if we should flush
                elapsed = time.time() - last_flush
                should_flush = (
                    len(batch) >= self.batch_size or
                    (len(batch) > 0 and elapsed >= self.flush_interval)
                )
                
                if should_flush:
                    self._write_batch(batch)
                    batch = []
                    last_flush = time.time()
                    
            except Exception as e:
                self.logger.error(f"Worker error: {e}")
        
        # Final flush on shutdown
        if batch:
            self._write_batch(batch)
    
    def _derive_timestamps(self, event: Event) -> tuple:
        """
        Derive start_ts and end_ts from event.
        
        Formula:
            end_ts = event.timestamp
            start_ts = end_ts - (event.correlation_age_ms / 1000.0)
        
        Returns:
            (start_ts, end_ts) as floats (epoch seconds)
        """
        end_ts = float(event.timestamp)
        correlation_age_sec = float(event.correlation_age_ms) / 1000.0
        start_ts = end_ts - correlation_age_sec
        
        # Ensure start_ts is never after end_ts
        if start_ts > end_ts:
            start_ts = end_ts
        
        return (start_ts, end_ts)
    
    def _normalize_event_type(self, event_type: str) -> str:
        """Normalize event type for DB storage."""
        # Remove "_detected" suffix if present
        normalized = event_type.lower().replace("_detected", "")
        return normalized
    
    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity for DB storage."""
        return severity.lower()
    
    def _write_batch(self, batch: List[Event]) -> None:
        """Write a batch of events to database."""
        if not batch:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Enable foreign keys for this connection
            cursor.execute("PRAGMA foreign_keys=ON;")
            
            for event in batch:
                try:
                    # Derive timestamps
                    start_ts, end_ts = self._derive_timestamps(event)
                    
                    # Normalize fields
                    event_type = self._normalize_event_type(event.event_type)
                    severity = self._normalize_severity(event.severity)
                    
                    cursor.execute(
                        """
                        INSERT INTO events 
                        (id, camera_id, event_type, severity, start_ts, end_ts, 
                         confidence, model_version, created_at, clip_status, clip_error, clip_updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.event_id,
                            event.camera_id,
                            event_type,
                            severity,
                            start_ts,
                            end_ts,
                            event.confidence,
                            self.model_version,
                            time.time(),
                            "pending",
                            None,
                            None,
                        )
                    )
                    self.events_written += 1
                    
                except sqlite3.IntegrityError as e:
                    # Duplicate or constraint violation - log and continue
                    self.write_failures += 1
                    self.logger.warning(
                        f"Event insert failed (integrity): {e}",
                        extra={"event_id": event.event_id}
                    )
                except sqlite3.Error as e:
                    self.write_failures += 1
                    self.logger.warning(
                        f"Event write failed: {e}",
                        extra={"event_id": event.event_id}
                    )
            
            conn.commit()
            conn.close()
            self.batches_written += 1
            
            self.logger.debug(
                f"Wrote batch of {len(batch)} events",
                extra={"batch_size": len(batch)}
            )
            
        except Exception as e:
            self.write_failures += len(batch)
            self.logger.error(f"Batch write failed: {e}")
    
    def write(self, event: Event) -> None:
        """
        Queue event for async database write.
        
        Non-blocking, fails independently.
        
        Args:
            event: Classified event
        """
        if not self.enabled:
            return
        
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.events_dropped += 1
            self.logger.warning(
                f"Write queue full, dropping event",
                extra={"event_id": event.event_id}
            )
    
    def shutdown(self) -> None:
        """Gracefully stop the writer, flushing pending events."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.logger.info("Database writer shutdown")
    
    def get_stats(self) -> dict:
        """Get writer statistics."""
        return {
            "enabled": self.enabled,
            "db_path": self.db_path,
            "events_written": self.events_written,
            "events_dropped": self.events_dropped,
            "write_failures": self.write_failures,
            "batches_written": self.batches_written,
            "queue_size": self._queue.qsize()
        }
