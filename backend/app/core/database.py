"""
VisionGuard AI - Database Management
Asynchronous PostgreSQL database connector using asyncpg.
"""

import asyncio
import logging
import asyncpg
from typing import Optional, List, Dict, Any, Union
from .config import get_settings

logger = logging.getLogger(__name__)

class Database:
    """
    Manages PostgreSQL connection pool and provides a clean interface for queries.
    """
    
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self.settings = get_settings()
        self.url = self.settings.get_database_url
        
    async def connect(self):
        """Initialize the connection pool."""
        if self._pool is not None:
            return
            
        try:
            logger.info(f"Connecting to PostgreSQL at {self.settings.postgres_host}:{self.settings.postgres_port}")
            self._pool = await asyncpg.create_pool(
                dsn=self.url,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info("PostgreSQL connection pool established")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def disconnect(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    async def fetch_all(self, query: str, *args) -> List[Dict[str, Any]]:
        """Execute a query and return all results as a list of dictionaries."""
        if not self._pool:
            await self.connect()
            
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def fetch_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Execute a query and return a single result as a dictionary."""
        if not self._pool:
            await self.connect()
            
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def execute(self, query: str, *args) -> str:
        """Execute a command (INSERT, UPDATE, DELETE)."""
        if not self._pool:
            await self.connect()
            
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def execute_many(self, query: str, args: List[tuple]):
        """Execute a command many times with different arguments."""
        if not self._pool:
            await self.connect()
            
        async with self._pool.acquire() as conn:
            return await conn.executemany(query, args)

# Global database instance
db = Database()

async def get_db() -> Database:
    """Dependency for getting the database instance."""
    if not db._pool:
        await db.connect()
    return db
