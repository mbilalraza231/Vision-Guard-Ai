import sqlite3
import uuid
import time
import logging
from typing import Optional, List, Dict, Any

from .config import AlertConfig

logger = logging.getLogger(__name__)


class AlertRepository:
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
        self.db_path = self.config.db_path
    
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    
    def create(self, event_id: str, channel: str = "webhook") -> Optional[str]:
        alert_id = str(uuid.uuid4())
        try:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO alerts (id, event_id, channel, status, attempts, last_attempt_ts, created_at)
                VALUES (?, ?, ?, 'pending', 0, NULL, ?)
                """,
                (alert_id, event_id, channel, time.time())
            )
            conn.commit()
            conn.close()
            return alert_id
        except sqlite3.IntegrityError:
            return None
        except Exception as e:
            logger.error(f"Alert create failed: {e}")
            return None
    
    def get_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Alert get failed: {e}")
            return None
    
    def get_pending_alerts(self, max_attempts: int = 5) -> List[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                """
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence, 
                       e.start_ts, e.end_ts, e.model_version
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                WHERE a.status IN ('pending', 'failed')
                AND a.attempts < ?
                ORDER BY a.created_at ASC
                """,
                (max_attempts,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Get pending alerts failed: {e}")
            return []
    
    def update_status(self, alert_id: str, status: str) -> bool:
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE alerts SET status = ?, last_attempt_ts = ? WHERE id = ?",
                (status, time.time(), alert_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Update status failed: {e}")
            return False
    
    def increment_attempts(self, alert_id: str) -> bool:
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE alerts SET attempts = attempts + 1, last_attempt_ts = ? WHERE id = ?",
                (time.time(), alert_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Increment attempts failed: {e}")
            return False
    
    def find_recent_alerts(
        self,
        camera_id: str,
        event_type: str,
        severity: str,
        since_ts: float
    ) -> List[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                """
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                WHERE e.camera_id = ?
                AND e.event_type = ?
                AND e.severity = ?
                AND a.status IN ('sent', 'acknowledged')
                AND a.created_at >= ?
                """,
                (camera_id, event_type, severity, since_ts)
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Find recent alerts failed: {e}")
            return []
    
    def list_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = None,
        severity: str = None,
        camera_id: str = None
    ) -> Dict[str, Any]:
        try:
            conn = self._get_conn()
            
            where_clauses = []
            params = []
            
            if status:
                where_clauses.append("a.status = ?")
                params.append(status)
            if severity:
                where_clauses.append("e.severity = ?")
                params.append(severity)
            if camera_id:
                where_clauses.append("e.camera_id = ?")
                params.append(camera_id)
            
            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)
            
            count_sql = f"""
                SELECT COUNT(*) FROM alerts a
                JOIN events e ON a.event_id = e.id
                {where_sql}
            """
            cursor = conn.execute(count_sql, params)
            total = cursor.fetchone()[0]
            
            query_sql = f"""
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence,
                       e.start_ts, e.end_ts
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                {where_sql}
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            cursor = conn.execute(query_sql, params)
            rows = cursor.fetchall()
            conn.close()
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "alerts": [dict(r) for r in rows]
            }
        except Exception as e:
            logger.error(f"List alerts failed: {e}")
            return {"total": 0, "limit": limit, "offset": offset, "alerts": []}
    
    def get_alert_with_event(self, alert_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                """
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence,
                       e.start_ts, e.end_ts, e.model_version, e.created_at as event_created_at
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                WHERE a.id = ?
                """,
                (alert_id,)
            )
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Get alert with event failed: {e}")
            return None
