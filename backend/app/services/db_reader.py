"""
VisionGuard AI - Database Reader Service

READ-ONLY database access for FastAPI backend.
Queries events from SQLite.
"""

import sqlite3
import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """Get database path from environment."""
    return os.getenv("VG_DB_PATH", "/data/visionguard/events.db")


@dataclass
class EventRow:
    """Event row from database."""
    id: str
    camera_id: str
    event_type: str
    severity: str
    start_ts: float
    end_ts: float
    confidence: float
    model_version: str
    created_at: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "confidence": self.confidence,
            "model_version": self.model_version,
            "created_at": self.created_at
        }


class DatabaseReader:
    """
    Read-only database reader for backend.
    
    Features:
    - Query events with pagination
    - Filter by camera, type, severity
    - Get single event by ID
    - Never writes to database
    """
    
    def __init__(self, db_path: str = None):
        """
        Initialize database reader.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or get_db_path()
        self.logger = logging.getLogger(__name__)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def list_events(
        self,
        limit: int = 50,
        offset: int = 0,
        camera_id: str = None,
        event_type: str = None,
        severity: str = None
    ) -> Dict[str, Any]:
        """
        List events with pagination and filtering.
        
        Args:
            limit: Max events to return (1-100)
            offset: Offset for pagination
            camera_id: Filter by camera ID
            event_type: Filter by event type
            severity: Filter by severity
            
        Returns:
            Dictionary with total, limit, offset, and events list
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Build query
            where_clauses = []
            params = []
            
            if camera_id:
                where_clauses.append("camera_id = ?")
                params.append(camera_id)
            
            if event_type:
                where_clauses.append("event_type = ?")
                params.append(event_type.lower().replace("_detected", ""))
            
            if severity:
                where_clauses.append("severity = ?")
                params.append(severity.lower())
            
            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)
            
            # Get total count
            count_sql = f"SELECT COUNT(*) FROM events {where_sql}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()[0]
            
            # Get events
            query_sql = f"""
                SELECT id, camera_id, event_type, severity, 
                       start_ts, end_ts, confidence, model_version, created_at
                FROM events 
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            
            conn.close()
            
            events = []
            for row in rows:
                events.append({
                    "id": row["id"],
                    "camera_id": row["camera_id"],
                    "event_type": row["event_type"],
                    "severity": row["severity"],
                    "start_ts": row["start_ts"],
                    "end_ts": row["end_ts"],
                    "confidence": row["confidence"],
                    "model_version": row["model_version"],
                    "created_at": row["created_at"]
                })
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "events": events
            }
            
        except FileNotFoundError:
            self.logger.warning("Database not found, returning empty results")
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "events": []
            }
        except Exception as e:
            self.logger.error(f"Error listing events: {e}")
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "events": [],
                "error": str(e)
            }
    
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single event by ID.
        
        Args:
            event_id: Event UUID
            
        Returns:
            Event dictionary or None if not found
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT id, camera_id, event_type, severity, 
                       start_ts, end_ts, confidence, model_version, created_at
                FROM events 
                WHERE id = ?
                """,
                (event_id,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row is None:
                return None
            
            return {
                "id": row["id"],
                "camera_id": row["camera_id"],
                "event_type": row["event_type"],
                "severity": row["severity"],
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "confidence": row["confidence"],
                "model_version": row["model_version"],
                "created_at": row["created_at"]
            }
            
        except FileNotFoundError:
            self.logger.warning("Database not found")
            return None
        except Exception as e:
            self.logger.error(f"Error getting event: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Total events
            cursor.execute("SELECT COUNT(*) FROM events")
            total_events = cursor.fetchone()[0]
            
            # Events by type
            cursor.execute(
                "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
            )
            by_type = dict(cursor.fetchall())
            
            # Events by severity
            cursor.execute(
                "SELECT severity, COUNT(*) FROM events GROUP BY severity"
            )
            by_severity = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                "total_events": total_events,
                "by_type": by_type,
                "by_severity": by_severity,
                "db_path": self.db_path
            }
            
        except Exception as e:
            return {"error": str(e)}


# Singleton instance for backend
_reader: Optional[DatabaseReader] = None


def get_db_reader() -> DatabaseReader:
    """Get or create the database reader instance."""
    global _reader
    if _reader is None:
        _reader = DatabaseReader()
    return _reader
