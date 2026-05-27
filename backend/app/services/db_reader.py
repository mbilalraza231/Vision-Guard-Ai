"""
VisionGuard AI - Database Reader Service

READ-ONLY database access for FastAPI backend.
Queries events from PostgreSQL.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from ..core.database import db

logger = logging.getLogger(__name__)


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
    Read-only asynchronous database reader for backend.
    """
    
    def __init__(self):
        """
        Initialize database reader.
        """
        self.logger = logging.getLogger(__name__)
    
    async def list_events(
        self,
        limit: int = 50,
        offset: int = 0,
        camera_id: str = None,
        event_type: str = None,
        severity: str = None,
        start_ts_gte: float = None
    ) -> Dict[str, Any]:
        """
        List events with pagination and filtering.
        """
        try:
            # Build query
            where_clauses = []
            params = []
            param_idx = 1
            
            if camera_id:
                where_clauses.append(f"camera_id = ${param_idx}")
                params.append(camera_id)
                param_idx += 1
            
            if event_type:
                where_clauses.append(f"event_type = ${param_idx}")
                params.append(event_type.lower().replace("_detected", ""))
                param_idx += 1
            
            if severity:
                where_clauses.append(f"severity = ${param_idx}")
                params.append(severity.lower())
                param_idx += 1
                
            if start_ts_gte is not None:
                where_clauses.append(f"start_ts >= ${param_idx}")
                params.append(start_ts_gte)
                param_idx += 1
            
            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)
            
            # Get total count
            count_sql = f"SELECT COUNT(*) FROM events {where_sql}"
            count_row = await db.fetch_one(count_sql, *params)
            total = count_row['count'] if count_row else 0
            
            # Get events with evidence URLs
            query_sql = f"""
                SELECT e.*, 
                       s.public_url as snapshot_url, 
                       s.storage_provider as snapshot_provider,
                       c.public_url as clip_url,
                       c.storage_provider as clip_provider
                FROM events e
                LEFT JOIN event_evidence s ON e.id = s.event_id AND s.evidence_type = 'snapshot'
                LEFT JOIN event_evidence c ON e.id = c.event_id AND c.evidence_type = 'clip'
                {where_sql}
                ORDER BY e.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])
            
            rows = await db.fetch_all(query_sql, *params)
            
            events = []
            for row in rows:
                ev = dict(row)
                
                # Translate local paths to API URLs
                snap_url = ev.get("snapshot_url")
                if snap_url and snap_url.startswith("/data/visionguard/detections/"):
                    filename = os.path.basename(snap_url)
                    ev["snapshot_url"] = f"/detections/images/{filename}"
                
                c_url = ev.get("clip_url")
                if c_url and c_url.startswith("/data/visionguard/clips/"):
                    filename = os.path.basename(c_url)
                    ev["clip_url"] = f"/detections/clips/{filename}"
                        
                events.append(ev)
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "events": events
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
    
    async def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single event by ID.
        """
        try:
            query_sql = """
                SELECT e.*, 
                       s.public_url as snapshot_url, 
                       s.storage_provider as snapshot_provider,
                       c.public_url as clip_url,
                       c.storage_provider as clip_provider
                FROM events e
                LEFT JOIN event_evidence s ON e.id = s.event_id AND s.evidence_type = 'snapshot'
                LEFT JOIN event_evidence c ON e.id = c.event_id AND c.evidence_type = 'clip'
                WHERE e.id = $1
            """
            row = await db.fetch_one(query_sql, event_id)
            
            if row is None:
                return None
            
            ev = dict(row)
            
            # Translate local paths to API URLs
            snap_url = ev.get("snapshot_url")
            if snap_url and snap_url.startswith("/data/visionguard/detections/"):
                filename = os.path.basename(snap_url)
                ev["snapshot_url"] = f"/detections/images/{filename}"
            
            c_url = ev.get("clip_url")
            if c_url and c_url.startswith("/data/visionguard/clips/"):
                filename = os.path.basename(c_url)
                ev["clip_url"] = f"/detections/clips/{filename}"
                    
            return ev
            
        except Exception as e:
            self.logger.error(f"Error getting event: {e}")
            return None
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            total_events_row = await db.fetch_one("SELECT COUNT(*) FROM events")
            total_events = total_events_row['count'] if total_events_row else 0
            
            by_type_rows = await db.fetch_all("SELECT event_type, COUNT(*) FROM events GROUP BY event_type")
            by_type = {r['event_type']: r['count'] for r in by_type_rows}
            
            by_severity_rows = await db.fetch_all("SELECT severity, COUNT(*) FROM events GROUP BY severity")
            by_severity = {r['severity']: r['count'] for r in by_severity_rows}
            
            # Calculate average confidence
            avg_conf_row = await db.fetch_one("SELECT AVG(confidence) FROM events")
            avg_confidence = avg_conf_row['avg'] if avg_conf_row and avg_conf_row['avg'] is not None else 0.0
            
            # Fetch recent confidence trend (last 15 events)
            trend_rows = await db.fetch_all(
                "SELECT id, event_type, confidence, created_at FROM events ORDER BY created_at DESC LIMIT 15"
            )
            confidence_history = [
                {
                    "id": r["id"],
                    "event_type": r["event_type"],
                    "confidence": r["confidence"],
                    "created_at": r["created_at"]
                }
                for r in reversed(trend_rows)
            ]
            
            # Calculate average processing delay (latency) over the last 50 events to reflect real-time performance
            avg_delay_row = await db.fetch_one("""
                SELECT AVG(created_at - start_ts) as avg 
                FROM (
                    SELECT created_at, start_ts 
                    FROM events 
                    WHERE created_at > start_ts 
                    ORDER BY created_at DESC 
                    LIMIT 50
                ) as recent
            """)
            avg_processing_delay = avg_delay_row['avg'] if avg_delay_row and avg_delay_row['avg'] is not None else 0.0
            
            # Calculate False Positive Rate (proxy: % of events with confidence < 0.50)
            low_conf_row = await db.fetch_one("SELECT COUNT(*) FROM events WHERE confidence < 0.50")
            low_conf_count = low_conf_row['count'] if low_conf_row else 0
            false_positive_rate = (low_conf_count / total_events * 100) if total_events > 0 else 0.0

            return {
                "total_events": total_events,
                "by_type": by_type,
                "by_severity": by_severity,
                "avg_confidence": avg_confidence,
                "confidence_history": confidence_history,
                "avg_processing_delay": avg_processing_delay,
                "false_positive_rate": false_positive_rate
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
