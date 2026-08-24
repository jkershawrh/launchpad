"""Regression tests for the synchronous PostgreSQL storage implementation."""

import asyncio
import sys
from types import SimpleNamespace

from app.storage import database
from app.storage.stores import _decode_json


def test_decode_json_accepts_native_jsonb_value():
    value = {"tenant_id": "tenant-a", "enabled": True}

    assert _decode_json(value) is value


def test_decode_json_accepts_serialized_value():
    assert _decode_json('{"tenant_id": "tenant-a"}') == {"tenant_id": "tenant-a"}


def test_init_db_uses_sync_driver_and_closes_connection(monkeypatch):
    events = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            events.append(("execute", sql, params))

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            events.append(("close",))

    driver = SimpleNamespace(
        connect=lambda url, connect_timeout: (
            events.append(("connect", url, connect_timeout)) or FakeConnection()
        )
    )
    monkeypatch.setitem(sys.modules, "psycopg2", driver)
    monkeypatch.setenv("LAUNCHPAD_MODE", "openshift")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/launchpad")
    monkeypatch.setattr(database, "_run_migrations", lambda conn: events.append(("migrate", conn)))

    assert asyncio.run(database.init_db()) is True
    assert events[0] == ("connect", "postgresql://db/launchpad", 5)
    assert events[1][0] == "execute"
    assert events[2][0] == "migrate"
    assert events[3] == ("close",)
