"""
Async PostgreSQL storage layer using asyncpg.

Graceful degradation: works without a database if DATABASE_URL is not set,
falling back to in-memory storage.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("launchpad.storage")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"

_pool = None


def get_database_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL")


def get_pool():
    return _pool


async def init_db() -> bool:
    """Initialize the asyncpg connection pool and run migrations.

    Returns True if connected, False if running without persistence.
    In mock mode, skip DB entirely so services use in-memory fallback.
    """
    global _pool
    mode = os.environ.get("LAUNCHPAD_MODE", "mock")
    if mode == "mock":
        logger.info("LAUNCHPAD_MODE=mock — skipping database, using in-memory storage")
        _pool = None
        return False
    url = get_database_url()
    if not url:
        logger.info("DATABASE_URL not set — running without persistence")
        return False
    try:
        import asyncpg
    except ImportError:
        logger.warning("asyncpg not installed — running without persistence")
        return False
    try:
        _pool = await asyncpg.create_pool(
            url, min_size=2, max_size=10,
            server_settings={"statement_timeout": "30000"},
        )
        logger.info("Connected to PostgreSQL")
        await _run_migrations()
        return True
    except Exception as e:
        logger.warning("Failed to connect to PostgreSQL: %s — running without persistence", e)
        _pool = None
        return False


async def close_db() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def _run_migrations() -> None:
    """Run numbered SQL migration files, tracking applied migrations."""
    if not _pool:
        return
    if not MIGRATIONS_DIR.exists():
        logger.debug("No migrations directory found at %s", MIGRATIONS_DIR)
        return
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        return
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """)
        for sql_file in sql_files:
            already = await conn.fetchval(
                "SELECT COUNT(*) FROM applied_migrations WHERE filename = $1",
                sql_file.name,
            )
            if already:
                logger.debug("Migration %s already applied", sql_file.name)
                continue
            sql = sql_file.read_text()
            try:
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO applied_migrations (filename) VALUES ($1)",
                    sql_file.name,
                )
                logger.info("Applied migration: %s", sql_file.name)
            except Exception as e:
                err_msg = str(e).lower()
                if "already exists" in err_msg or "duplicate" in err_msg:
                    logger.debug("Migration %s already applied (idempotent)", sql_file.name)
                else:
                    logger.error("Migration %s failed: %s", sql_file.name, e)
                    raise
