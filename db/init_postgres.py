"""
VisionGuard AI - PostgreSQL Initialization
Handles table creation and schema verification for PostgreSQL.
"""

import asyncio
import os
import logging
import asyncpg
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_postgres():
    """Initialize PostgreSQL database with schema."""
    user = os.getenv("VG_POSTGRES_USER", "postgres")
    password = os.getenv("VG_POSTGRES_PASSWORD", "postgres")
    db_name = os.getenv("VG_POSTGRES_DB", "visionguard")
    host = os.getenv("VG_POSTGRES_HOST", "localhost")
    port = os.getenv("VG_POSTGRES_PORT", "5432")
    
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    
    # Path to schema file
    schema_path = Path(__file__).parent / "postgres_schema.sql"
    if not schema_path.exists():
        logger.error(f"Schema file not found at {schema_path}")
        return False

    with open(schema_path, "r") as f:
        schema_sql = f.read()

    logger.info(f"Connecting to PostgreSQL at {host}:{port}...")
    
    try:
        # Connect to default postgres database first to ensure the target DB exists
        conn = await asyncpg.connect(user=user, password=password, host=host, port=port, database="postgres")
        try:
            # Check if database exists
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
            if not exists:
                logger.info(f"Creating database {db_name}...")
                # Cannot use parameters for CREATE DATABASE
                await conn.execute(f"CREATE DATABASE {db_name}")
            else:
                logger.info(f"Database {db_name} already exists.")
        finally:
            await conn.close()

        # Connect to the target database and run schema
        conn = await asyncpg.connect(url)
        try:
            logger.info("Executing schema...")
            await conn.execute(schema_sql)
            logger.info("✅ PostgreSQL initialization successful")
            return True
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"❌ PostgreSQL initialization failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(init_postgres())
