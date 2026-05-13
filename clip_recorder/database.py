"""
VisionGuard AI - Database Management for Clip Recorder
"""

import logging
import asyncpg
from typing import Optional, List, Dict, Any
from .config import ClipConfig

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, config: ClipConfig):
        self._pool: Optional[asyncpg.Pool] = None
        self.config = config
        self.url = self.config.get_database_url()
        
    async def connect(self):
        if self._pool is not None:
            return
            
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self.url,
                min_size=1,
                max_size=5,
            )
            logger.info("PostgreSQL connection pool established for Clip Recorder")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def disconnect(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def fetch_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        if not self._pool:
            await self.connect()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def execute(self, query: str, *args) -> str:
        if not self._pool:
            await self.connect()
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)
