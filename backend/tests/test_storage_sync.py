"""Regression tests for the synchronous PostgreSQL storage implementation."""

import asyncio
import sys
from collections import deque
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from app.domain.access import AccessPolicy
from app.domain.enums import SessionStatus, WorkshopStatus
from app.domain.models import LabSession, Workshop
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


class _WorkshopCursor:
    def __init__(self, existing=None):
        self.existing = existing
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split()), params))

    def fetchone(self):
        return (self.existing.model_dump(mode="json"),) if self.existing else None


class _WorkshopConnection:
    def __init__(self, existing=None):
        self.cursor_value = _WorkshopCursor(existing)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _keyed_workshop(*, seats=2, workshop_id="workshop-1"):
    return Workshop(
        workshop_id=workshop_id,
        tenant_id="tenant-1",
        catalog_item_id="catalog-1",
        num_users=seats,
        status=WorkshopStatus.AWAITING_CONFIRMATION,
        idempotency_key="event-order-1",
        order_fingerprint=f"fingerprint-{seats}",
    )


def test_workshop_create_idempotent_takes_transaction_lock_before_insert(monkeypatch):
    connection = _WorkshopConnection()
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)
    workshop = _keyed_workshop()

    persisted = stores.PostgresWorkshopStore().create_idempotent(workshop)

    assert persisted == workshop
    statements = [statement for statement, _params in connection.cursor_value.statements]
    assert "pg_advisory_xact_lock" in statements[0]
    assert "FOR UPDATE" in statements[1]
    assert statements[2].startswith("INSERT INTO workshops")
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed


def test_workshop_create_idempotent_recovers_existing_matching_order(monkeypatch):
    existing = _keyed_workshop(workshop_id="accepted-by-other-replica")
    connection = _WorkshopConnection(existing)
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)

    persisted = stores.PostgresWorkshopStore().create_idempotent(_keyed_workshop())

    assert persisted.workshop_id == "accepted-by-other-replica"
    assert len(connection.cursor_value.statements) == 2
    assert connection.commits == 1


def test_workshop_create_idempotent_rejects_conflicting_order(monkeypatch):
    existing = _keyed_workshop(seats=3, workshop_id="accepted-by-other-replica")
    connection = _WorkshopConnection(existing)
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)

    with pytest.raises(
        stores.WorkshopIdempotencyConflictError,
        match="different workshop order",
    ):
        stores.PostgresWorkshopStore().create_idempotent(_keyed_workshop(seats=2))

    assert connection.commits == 0
    assert connection.rollbacks == 1


class _PolicyCursor:
    def __init__(self, rows):
        self.rows = deque(rows)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split()), params))

    def fetchone(self):
        value = self.rows.popleft()
        return (value.model_dump(mode="json"),) if value else None


class _PolicyConnection:
    def __init__(self, rows):
        self.cursor_value = _PolicyCursor(rows)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _access_policy(*, order_id="order-1", public_url="https://labs.example.io"):
    return AccessPolicy(
        order_id=order_id,
        order_type="workshop",
        catalog_slug="agent-lab",
        code_hash="$argon2id$authoritative-hash",
        seat_refs=["seat-1"],
        public_url=public_url,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )


def test_public_policy_is_inserted_once_behind_order_and_origin_locks(monkeypatch):
    connection = _PolicyConnection([None, None])
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)
    policy = _access_policy()

    persisted, created = stores.PostgresAccessStore().create_policy_once(
        policy, now=datetime.utcnow()
    )

    assert created is True
    assert persisted == policy
    statements = [statement for statement, _params in connection.cursor_value.statements]
    assert sum("pg_advisory_xact_lock" in statement for statement in statements) == 2
    assert statements[-1].startswith("INSERT INTO access_policies")
    assert connection.commits == 1


def test_public_policy_concurrent_loser_recovers_authoritative_hash(monkeypatch):
    existing = _access_policy()
    connection = _PolicyConnection([existing])
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)

    persisted, created = stores.PostgresAccessStore().create_policy_once(
        _access_policy(), now=datetime.utcnow()
    )

    assert created is False
    assert persisted.code_hash == existing.code_hash
    assert len(connection.cursor_value.statements) == 3
    assert connection.commits == 1


def test_public_policy_rejects_another_active_order_on_same_origin(monkeypatch):
    existing = _access_policy(order_id="other-order")
    connection = _PolicyConnection([None, existing])
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)

    with pytest.raises(
        stores.PublicAccessPolicyConflictError,
        match="active order",
    ):
        stores.PostgresAccessStore().create_policy_once(
            _access_policy(), now=datetime.utcnow()
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


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
