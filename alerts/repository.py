import uuid
import time
import logging
from typing import Optional, List, Dict, Any

from .config import AlertConfig
from backend.app.core.database import db

logger = logging.getLogger(__name__)


class AlertRepository:
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
    
    async def create(
        self, 
        event_id: str, 
        channel: str = "webhook", 
        recipient: str = None, 
        status: str = "pending"
    ) -> Optional[str]:
        alert_id = str(uuid.uuid4())
        try:
            await db.execute(
                """
                INSERT INTO alerts (id, event_id, channel, recipient, status, attempts, last_attempt_ts, created_at)
                VALUES ($1, $2, $3, $4, $5, 0, NULL, $6)
                """,
                alert_id, event_id, channel, recipient, status, time.time()
            )
            return alert_id
        except Exception as e:
            logger.error(f"Alert create failed: {e}")
            return None
    
    async def get_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        try:
            row = await db.fetch_one("SELECT * FROM alerts WHERE id = $1", alert_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Alert get failed: {e}")
            return None
    
    async def get_pending_alerts(self, max_attempts: int = 5) -> List[Dict[str, Any]]:
        try:
            rows = await db.fetch_all(
                """
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence, 
                       e.start_ts, e.end_ts, e.model_version
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                WHERE a.status IN ('pending', 'failed')
                AND a.attempts < $1
                ORDER BY a.created_at ASC
                """,
                max_attempts
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Get pending alerts failed: {e}")
            return []
    
    async def update_status(self, alert_id: str, status: str) -> bool:
        try:
            await db.execute(
                "UPDATE alerts SET status = $1, last_attempt_ts = $2 WHERE id = $3",
                status, time.time(), alert_id
            )
            return True
        except Exception as e:
            logger.error(f"Update status failed: {e}")
            return False
    
    async def increment_attempts(self, alert_id: str) -> bool:
        try:
            await db.execute(
                "UPDATE alerts SET attempts = attempts + 1, last_attempt_ts = $1 WHERE id = $2",
                time.time(), alert_id
            )
            return True
        except Exception as e:
            logger.error(f"Increment attempts failed: {e}")
            return False
    
    async def find_recent_alerts(
        self,
        camera_id: str,
        event_type: str,
        severity: str,
        since_ts: float
    ) -> List[Dict[str, Any]]:
        try:
            rows = await db.fetch_all(
                """
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                WHERE e.camera_id = $1
                AND e.event_type = $2
                AND e.severity = $3
                AND a.status IN ('sent', 'acknowledged')
                AND a.created_at >= $4
                """,
                camera_id, event_type, severity, since_ts
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Find recent alerts failed: {e}")
            return []

    async def get_active_contacts(self) -> List[Dict[str, Any]]:
        """Fetch all active alert contacts."""
        try:
            rows = await db.fetch_all(
                "SELECT * FROM alert_contacts WHERE is_active = TRUE"
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Get active contacts failed: {e}")
            return []
    
    async def list_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = None,
        severity: str = None,
        camera_id: str = None
    ) -> Dict[str, Any]:
        try:
            where_clauses = []
            params = []
            param_idx = 1
            
            if status:
                where_clauses.append(f"a.status = ${param_idx}")
                params.append(status)
                param_idx += 1
            if severity:
                where_clauses.append(f"e.severity = ${param_idx}")
                params.append(severity)
                param_idx += 1
            if camera_id:
                where_clauses.append(f"e.camera_id = ${param_idx}")
                params.append(camera_id)
                param_idx += 1
            
            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)
            
            count_sql = f"""
                SELECT COUNT(*) FROM alerts a
                JOIN events e ON a.event_id = e.id
                {where_sql}
            """
            count_row = await db.fetch_one(count_sql, *params)
            total = count_row['count'] if count_row else 0
            
            query_sql = f"""
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence,
                       e.start_ts, e.end_ts
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                {where_sql}
                ORDER BY a.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])
            rows = await db.fetch_all(query_sql, *params)
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "alerts": [dict(r) for r in rows]
            }
        except Exception as e:
            logger.error(f"List alerts failed: {e}")
            return {"total": 0, "limit": limit, "offset": offset, "alerts": []}
    
    async def get_alert_with_event(self, alert_id: str) -> Optional[Dict[str, Any]]:
        try:
            row = await db.fetch_one(
                """
                SELECT a.*, e.camera_id, e.event_type, e.severity, e.confidence,
                       e.start_ts, e.end_ts, e.model_version, e.created_at as event_created_at
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                WHERE a.id = $1
                """,
                alert_id
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Get alert with event failed: {e}")
            return None
