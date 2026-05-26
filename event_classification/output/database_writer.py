"""
VisionGuard AI - Database Writer

Production PostgreSQL-based event persistence.
WRITE-ONLY access from ECS.
"""

import logging
import psycopg2
from psycopg2.extras import execute_values
import threading
import queue
import time
import os
from typing import Optional, List, Any

from ..classification.event_models import Event


class DatabaseWriter:
    """
    Production database writer for classified events.
    
    Features:
    - PostgreSQL for centralized storage
    - Async writes via background thread
    - Batched inserts for efficiency
    - Failure never blocks ECS
    - Derives start_ts/end_ts from correlation_age_ms
    
    WRITE-ONLY: ECS is the sole writer.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        database_url: str = None,
        postgres_config: dict = None,
        batch_size: int = 10,
        flush_interval_sec: float = 5.0,
        max_queue_size: int = 5000,
        model_version: str = None
    ):
        """
        Initialize database writer.
        
        Args:
            enabled: Whether writing is enabled
            database_url: PostgreSQL connection URL
            postgres_config: Dict with user, password, host, port, db
            batch_size: Number of events to batch before writing
            flush_interval_sec: Max time before forcing a write
            max_queue_size: Max pending events before dropping
            model_version: Model version string for DB records
        """
        self.logger = logging.getLogger(__name__)
        self.enabled = enabled
        
        if database_url:
            self.dsn = database_url
        elif postgres_config:
            self.dsn = f"postgresql://{postgres_config['user']}:{postgres_config['password']}@{postgres_config['host']}:{postgres_config['port']}/{postgres_config['db']}"
        else:
            # Fallback to env vars
            user = os.getenv("VG_POSTGRES_USER", "postgres")
            pw = os.getenv("VG_POSTGRES_PASSWORD", "postgres")
            db = os.getenv("VG_POSTGRES_DB", "visionguard")
            host = os.getenv("VG_POSTGRES_HOST", "postgres")
            port = os.getenv("VG_POSTGRES_PORT", "5432")
            self.dsn = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

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
            self._start_worker()
        
        self.logger.info(
            f"Database writer initialized (PostgreSQL)",
            extra={"enabled": enabled}
        )
    
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
        """Derive start_ts and end_ts from event."""
        end_ts = float(event.timestamp)
        correlation_age_sec = float(event.correlation_age_ms) / 1000.0
        start_ts = end_ts - correlation_age_sec
        if start_ts > end_ts:
            start_ts = end_ts
        return (start_ts, end_ts)
    
    def _is_anonymize_enabled(self) -> bool:
        """Check if data anonymization is enabled in system settings (cached for 30s)."""
        now = time.time()
        if not hasattr(self, "_last_privacy_check") or now - self._last_privacy_check > 30:
            self._last_privacy_check = now
            self._anonymize_cached = False
            conn = None
            try:
                import json
                conn = psycopg2.connect(self.dsn, connect_timeout=5)
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM system_settings ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if row and row[0]:
                    stored = row[0]
                    if isinstance(stored, str):
                        stored = json.loads(stored)
                    self._anonymize_cached = stored.get("privacy", {}).get("anonymizeData", False)
            except Exception as e:
                self.logger.warning(f"Failed to fetch privacy settings in DB writer: {e}")
            finally:
                if conn:
                    conn.close()
        return getattr(self, "_anonymize_cached", False)

    def _write_batch(self, batch: List[Event]) -> None:
        """Write a batch of events to database."""
        if not batch:
            return
        
        conn = None
        try:
            conn = psycopg2.connect(self.dsn, connect_timeout=10)
            cursor = conn.cursor()
            
            data = []
            anonymize = self._is_anonymize_enabled()
            for event in batch:
                start_ts, end_ts = self._derive_timestamps(event)
                
                cam_id = event.camera_id
                if anonymize:
                    if len(cam_id) > 4:
                        cam_id = cam_id[:2] + "****" + cam_id[-2:]
                    else:
                        cam_id = "****"

                data.append((
                    event.event_id,
                    cam_id,
                    event.event_type.lower().replace("_detected", ""),
                    event.severity.lower(),
                    start_ts,
                    end_ts,
                    event.confidence,
                    self.model_version,
                    time.time(),
                    "pending"
                ))

            execute_values(cursor, """
                INSERT INTO events 
                (id, camera_id, event_type, severity, start_ts, end_ts, 
                 confidence, model_version, created_at, clip_status)
                VALUES %s
                ON CONFLICT (id) DO NOTHING
            """, data)
            
            conn.commit()
            self.events_written += len(batch)
            self.batches_written += 1
            
        except Exception as e:
            self.write_failures += len(batch)
            self.logger.error(f"PostgreSQL batch write failed: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def write(self, event: Event) -> None:
        """Queue event for async database write."""
        if not self.enabled:
            return
        
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.events_dropped += 1
            self.logger.warning(f"Write queue full, dropping event {event.event_id}")
    
    def shutdown(self) -> None:
        """Gracefully stop the writer."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.logger.info("Database writer shutdown")

    def get_stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "events_written": self.events_written,
            "events_dropped": self.events_dropped,
            "write_failures": self.write_failures,
            "batches_written": self.batches_written,
            "queue_size": self._queue.qsize()
        }
