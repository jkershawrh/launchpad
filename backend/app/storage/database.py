from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.sql import func

metadata = MetaData()

tenants_table = Table(
    "tenants", metadata,
    Column("tenant_id", String, primary_key=True),
    Column("data", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

lab_requests_table = Table(
    "lab_requests", metadata,
    Column("request_id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("catalog_item_id", String, nullable=False),
    Column("status", String, nullable=False, index=True),
    Column("data", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

lab_sessions_table = Table(
    "lab_sessions", metadata,
    Column("session_id", String, primary_key=True),
    Column("request_id", String, nullable=False),
    Column("tenant_id", String, nullable=False, index=True),
    Column("catalog_item_id", String, nullable=False),
    Column("status", String, nullable=False, index=True),
    Column("namespace", Text),
    Column("data", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

provisioning_plans_table = Table(
    "provisioning_plans", metadata,
    Column("plan_id", String, primary_key=True),
    Column("request_id", String, nullable=False),
    Column("data", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

showback_records_table = Table(
    "showback_records", metadata,
    Column("showback_id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("session_id", String, nullable=False, index=True),
    Column("data", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

catalog_items_custom_table = Table(
    "catalog_items_custom", metadata,
    Column("catalog_item_id", String, primary_key=True),
    Column("data", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

_engine: Optional[Engine] = None


def get_database_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL")


def get_engine() -> Optional[Engine]:
    global _engine
    if _engine is not None:
        return _engine
    url = get_database_url()
    if not url:
        return None
    _engine = create_engine(url, pool_size=5, max_overflow=10)
    return _engine


def init_db() -> bool:
    engine = get_engine()
    if not engine:
        return False
    metadata.create_all(engine)
    return True


def close_db() -> None:
    global _engine
    if _engine:
        _engine.dispose()
        _engine = None
