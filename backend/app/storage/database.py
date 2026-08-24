"""
PostgreSQL initialization and migration support using psycopg2.

Graceful degradation: works without a database if DATABASE_URL is not set,
falling back to in-memory storage.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("launchpad.storage")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def get_database_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL")


async def init_db() -> bool:
    """Verify the database connection and run migrations.

    Returns True if connected, False if running without persistence.
    In mock mode, skip DB entirely so services use in-memory fallback.
    Store calls are synchronous, so no event-loop-bound connection pool is kept.
    """
    mode = os.environ.get("LAUNCHPAD_MODE", "mock")
    if mode == "mock":
        logger.info("LAUNCHPAD_MODE=mock — skipping database, using in-memory storage")
        return False
    url = get_database_url()
    if not url:
        logger.info("DATABASE_URL not set — running without persistence")
        return False
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not installed — running without persistence")
        return False
    try:
        await asyncio.to_thread(_initialize_database, psycopg2, url)
        logger.info("Connected to PostgreSQL and applied migrations")
        return True
    except Exception as e:
        logger.warning("Failed to connect to PostgreSQL: %s — running without persistence", e)
        return False


async def close_db() -> None:
    """No-op retained for the application lifespan interface."""


def _initialize_database(psycopg2, url: str) -> None:
    """Connect and migrate outside the application's event-loop thread."""
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
        _run_migrations(conn)
    finally:
        conn.close()


def _run_migrations(conn) -> None:
    """Run numbered SQL migration files, tracking applied migrations."""
    if not MIGRATIONS_DIR.exists():
        logger.debug("No migrations directory found at %s", MIGRATIONS_DIR)
        return
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        return
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """)
        for sql_file in sql_files:
            cur.execute(
                "SELECT COUNT(*) FROM applied_migrations WHERE filename = %s",
                (sql_file.name,),
            )
            already = cur.fetchone()[0]
            if already:
                logger.debug("Migration %s already applied", sql_file.name)
                continue
            sql = sql_file.read_text()
            try:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO applied_migrations (filename) VALUES (%s)",
                    (sql_file.name,),
                )
                logger.info("Applied migration: %s", sql_file.name)
            except Exception as e:
                conn.rollback()
                logger.error("Migration %s failed: %s", sql_file.name, e)
                raise
        conn.commit()
