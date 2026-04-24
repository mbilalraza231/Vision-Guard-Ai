"""
VisionGuard AI - Database Initialization

Production-ready SQLite initialization.
WAL mode, foreign keys, idempotent.
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


# =============================================================
# PRODUCTION SCHEMA (DO NOT MODIFY)
# =============================================================

SCHEMA_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,               -- UUID v4
    camera_id TEXT NOT NULL,
    event_type TEXT NOT NULL,           -- weapon | fire | fall | ...
    severity TEXT NOT NULL,             -- critical | high | medium
    start_ts REAL NOT NULL,             -- epoch (seconds)
    end_ts REAL NOT NULL,
    confidence REAL NOT NULL,           -- 0.0 – 1.0
    model_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    clip_status TEXT NOT NULL DEFAULT 'pending',   -- pending | ready | failed
    clip_error TEXT,
    clip_updated_at REAL
);

CREATE INDEX IF NOT EXISTS idx_events_camera_created 
    ON events(camera_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type_severity 
    ON events(event_type, severity);
"""

SCHEMA_EVENT_EVIDENCE = """
CREATE TABLE IF NOT EXISTS event_evidence (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,         -- clip | snapshot
    storage_provider TEXT,               -- cloudinary | s3 | local
    public_url TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(id)
);
"""

SCHEMA_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    channel TEXT NOT NULL,               -- webhook | email | sms
    status TEXT NOT NULL,                -- pending | sent | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_ts REAL,
    created_at REAL NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(id)
);
"""


def _ensure_events_clip_columns(cursor: sqlite3.Cursor) -> None:
    """Backfill clip lifecycle columns for existing databases."""
    cursor.execute("PRAGMA table_info(events)")
    cols = {row[1] for row in cursor.fetchall()}

    if "clip_status" not in cols:
        cursor.execute(
            "ALTER TABLE events ADD COLUMN clip_status TEXT NOT NULL DEFAULT 'pending'"
        )
    if "clip_error" not in cols:
        cursor.execute("ALTER TABLE events ADD COLUMN clip_error TEXT")
    if "clip_updated_at" not in cols:
        cursor.execute("ALTER TABLE events ADD COLUMN clip_updated_at REAL")


def get_db_path() -> str:
    """Get database path from environment."""
    return os.getenv("VG_DB_PATH", "/data/visionguard/events.db")


def init_database(db_path: str = None) -> bool:
    """
    Initialize database with production schema.
    
    Features:
    - WAL mode enabled
    - Foreign keys enabled
    - Auto-creates parent directories
    - Idempotent (safe on restart)
    
    Args:
        db_path: Path to SQLite database file (defaults to VG_DB_PATH env)
        
    Returns:
        True if initialization successful
    """
    if db_path is None:
        db_path = get_db_path()
    
    try:
        # Ensure parent directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Enable WAL mode
        cursor.execute("PRAGMA journal_mode=WAL;")
        wal_mode = cursor.fetchone()[0]
        logger.info(f"WAL mode: {wal_mode}")
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys=ON;")
        
        # Create tables
        cursor.executescript(SCHEMA_EVENTS)
        cursor.executescript(SCHEMA_EVENT_EVIDENCE)
        cursor.executescript(SCHEMA_ALERTS)
        _ensure_events_clip_columns(cursor)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Database initialized: {db_path}")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def verify_schema(db_path: str = None) -> dict:
    """
    Verify database schema is correct.
    
    Returns:
        Dictionary with table verification results
    """
    if db_path is None:
        db_path = get_db_path()
    
    results = {
        "db_exists": os.path.exists(db_path),
        "tables": {},
        "wal_enabled": False,
        "foreign_keys_enabled": False
    }
    
    if not results["db_exists"]:
        return results
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check WAL mode
        cursor.execute("PRAGMA journal_mode;")
        results["wal_enabled"] = cursor.fetchone()[0].upper() == "WAL"
        
        # Check foreign keys
        cursor.execute("PRAGMA foreign_keys;")
        results["foreign_keys_enabled"] = cursor.fetchone()[0] == 1
        
        # Check tables
        for table in ["events", "event_evidence", "alerts"]:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            results["tables"][table] = cursor.fetchone() is not None
        
        conn.close()
        
    except Exception as e:
        results["error"] = str(e)
    
    return results


if __name__ == "__main__":
    # CLI initialization
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    if init_database(db_path):
        print("✅ Database initialized successfully")
        print(verify_schema(db_path))
    else:
        print("❌ Database initialization failed")
        sys.exit(1)
