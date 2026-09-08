"""Regression tests for the synchronous PostgreSQL storage implementation."""

import asyncio
import sys
from types import SimpleNamespace

import pytest
from app.domain.enums import SessionStatus
from app.domain.models import LabSession
from app.storage import database, stores
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


def test_configured_database_connection_failure_is_not_silent(monkeypatch):
    class ConnectionFailure(Exception):
        pass

    driver = SimpleNamespace(
        connect=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ConnectionFailure("database unavailable")
        )
    )
    monkeypatch.setitem(sys.modules, "psycopg2", driver)
    monkeypatch.setattr(
        stores, "get_database_url", lambda: "postgresql://db/launchpad"
    )

    with pytest.raises(stores.PersistenceUnavailableError):
        stores._get_sync_conn()


def test_session_write_failure_is_not_downgraded_to_memory_only(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            raise RuntimeError("connection lost during write")

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(stores, "_get_sync_conn", lambda: FakeConnection())
    session = LabSession(
        request_id="request-1",
        tenant_id="tenant-1",
        catalog_item_id="catalog-1",
        namespace="launchpad-seat-1",
        status=SessionStatus.PROVISIONING,
    )

    with pytest.raises(stores.PersistenceUnavailableError):
        stores.PostgresSessionStore().save(session)


@pytest.mark.parametrize(
    ("store", "method", "args"),
    [
        (stores.PostgresSessionStore(), "get", ("session-1",)),
        (stores.PostgresSessionStore(), "list_all", ()),
        (stores.PostgresRequestStore(), "get", ("request-1",)),
        (stores.PostgresRequestStore(), "list_all", ()),
        (stores.PostgresWorkshopStore(), "get", ("workshop-1",)),
        (stores.PostgresWorkshopStore(), "list_all", ()),
    ],
)
def test_authoritative_lifecycle_read_failure_is_not_returned_as_missing(
    monkeypatch,
    store,
    method,
    args,
):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            raise RuntimeError("connection lost during read")

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(stores, "_get_sync_conn", lambda: FakeConnection())

    with pytest.raises(stores.PersistenceUnavailableError):
        getattr(store, method)(*args)
