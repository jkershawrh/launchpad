from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from app.domain.events import (
    EventCapacitySupply,
    EventCatalogCapacity,
    EventClusterCapacity,
    EventRecord,
    EventResourceVector,
    calculate_event_capacity,
)
from app.services.event_reservations import (
    EventReservationConflictError,
    EventReservationLedger,
    EventReservationUnavailableError,
    build_event_reservation_plan,
)
from app.storage import stores
from app.storage.stores import PostgresEventReservationStore

from backend.tests.test_event_capacity_matrix import _manifest

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "backend" / "migrations" / "008_event_capacity_reservations.sql"
CONTRACT = ROOT / "contracts" / "event-reservation-v1.yaml"
NOW = datetime(2026, 9, 19, 18, 0, tzinfo=UTC)


def _supply(*, seats: int = 60, cpu_millicores: int = 60_000) -> EventCapacitySupply:
    return EventCapacitySupply(
        matrix_id="matrix-v3",
        matrix_digest="sha256:" + "a" * 64,
        fleet_snapshot_id="sha256:" + "b" * 64,
        fleet_observed_at=NOW,
        clusters=[
            EventClusterCapacity(
                cluster_id="arena",
                enabled=True,
                exposure_policies=["public_code"],
                capabilities=["cpu", "model-endpoint"],
                certified_seats=seats,
                resource_capacity=EventResourceVector(
                    cpu_millicores=cpu_millicores,
                    memory_mib=120_000,
                    pods=180,
                    storage_gib=600,
                    routes=180,
                    model_slots=60,
                ),
                catalogs=[
                    EventCatalogCapacity(
                        catalog_id="serve-llms",
                        catalog_release="v1",
                        certified_seats=seats,
                        resources_per_seat=EventResourceVector(
                            cpu_millicores=1_000,
                            memory_mib=2_000,
                            pods=3,
                            storage_gib=10,
                            routes=3,
                            model_slots=1,
                        ),
                    ),
                    EventCatalogCapacity(
                        catalog_id="build-agent",
                        catalog_release="v2",
                        certified_seats=seats,
                        resources_per_seat=EventResourceVector(
                            cpu_millicores=1_000,
                            memory_mib=2_000,
                            pods=3,
                            storage_gib=10,
                            routes=3,
                            model_slots=1,
                        ),
                    ),
                ],
            )
        ],
    )


def _record(event_id: str, supply: EventCapacitySupply) -> EventRecord:
    manifest = _manifest()
    manifest.event_id = event_id
    return EventRecord(
        manifest=manifest,
        capacity_preview=calculate_event_capacity(manifest, supply),
        created_at=NOW,
    )


def _plan(event_id: str, supply: EventCapacitySupply):
    return build_event_reservation_plan(
        _record(event_id, supply),
        supply,
        expires_at=NOW + timedelta(hours=8),
        now=NOW,
    )


def test_plan_multiplies_server_owned_per_seat_resources():
    plan = _plan("event-a", _supply())

    assert len(plan.reservations) == 2
    assert sum(item.resources.seats for item in plan.reservations) == 60
    assert sum(item.resources.cpu_millicores for item in plan.reservations) == 60_000
    assert all(item.cluster_ref == "arena" for item in plan.reservations)
    assert all(item.matrix_id == "matrix-v3" for item in plan.reservations)
    assert all(item.fleet_snapshot_id == "sha256:" + "b" * 64 for item in plan.reservations)


def test_plan_rejects_capacity_evidence_drift():
    supply = _supply()
    record = _record("event-a", supply)
    supply.matrix_digest = "sha256:" + "c" * 64

    with pytest.raises(EventReservationConflictError, match="capacity evidence changed"):
        build_event_reservation_plan(
            record,
            supply,
            expires_at=NOW + timedelta(hours=8),
            now=NOW,
        )


def test_plan_rejects_missing_resource_footprint_and_stale_fleet_evidence():
    supply = _supply()
    supply.clusters[0].catalogs[0].resources_per_seat = EventResourceVector()
    record = _record("event-a", supply)

    with pytest.raises(EventReservationConflictError, match="resource footprint"):
        build_event_reservation_plan(
            record,
            supply,
            expires_at=NOW + timedelta(hours=8),
            now=NOW,
        )

    supply = _supply()
    record = _record("event-b", supply)
    with pytest.raises(EventReservationConflictError, match="Fleet snapshot is stale"):
        build_event_reservation_plan(
            record,
            supply,
            expires_at=NOW + timedelta(hours=8),
            now=NOW + timedelta(seconds=121),
        )


def test_concurrent_events_cannot_overbook_one_cluster():
    supply = _supply(seats=60, cpu_millicores=60_000)
    ledger = EventReservationLedger()
    plans = [_plan("event-a", supply), _plan("event-b", supply)]

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda plan: _reserve_outcome(ledger, plan, supply),
                plans,
            )
        )

    assert sorted(outcomes) == ["reserved", "unavailable"]
    assert sum(
        item.resources.seats for item in ledger.list_active(now=NOW)
    ) == 60


def test_same_event_reservation_is_idempotent_but_changed_plan_conflicts():
    supply = _supply()
    ledger = EventReservationLedger()
    plan = _plan("event-a", supply)

    first = ledger.reserve(plan, supply, now=NOW)
    repeated = ledger.reserve(plan, supply, now=NOW)

    assert repeated == first
    changed = plan.model_copy(deep=True)
    changed.reservations[0].resources.cpu_millicores += 1
    with pytest.raises(EventReservationConflictError, match="different reservation plan"):
        ledger.reserve(changed, supply, now=NOW)


def test_ledger_rejects_tampered_resource_claim_before_hold():
    supply = _supply()
    ledger = EventReservationLedger()
    changed = _plan("event-a", supply).model_copy(deep=True)
    changed.reservations[0].resources.cpu_millicores = 1

    with pytest.raises(
        EventReservationConflictError,
        match="do not match the certified catalog footprint",
    ):
        ledger.reserve(changed, supply, now=NOW)
    assert ledger.list_active(now=NOW) == []


def test_release_is_idempotent_and_frees_capacity():
    supply = _supply()
    ledger = EventReservationLedger()
    ledger.reserve(_plan("event-a", supply), supply, now=NOW)

    assert ledger.release("event-a", now=NOW + timedelta(minutes=5)) == 2
    assert ledger.release("event-a", now=NOW + timedelta(minutes=6)) == 0
    assert ledger.reserve(_plan("event-b", supply), supply, now=NOW)


def test_expired_holds_do_not_block_new_reservations():
    supply = _supply()
    ledger = EventReservationLedger()
    first = build_event_reservation_plan(
        _record("event-a", supply),
        supply,
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    ledger.reserve(first, supply, now=NOW)

    later = NOW + timedelta(minutes=2)
    second = build_event_reservation_plan(
        _record("event-b", supply),
        supply,
        expires_at=later + timedelta(hours=8),
        now=later,
    )
    assert ledger.reserve(second, supply, now=later)
    assert {item.event_id for item in ledger.list_active(now=later)} == {"event-b"}


def test_reservation_contract_and_migration_are_fail_closed():
    contract = yaml.safe_load(CONTRACT.read_text())
    schemas = contract["components"]["schemas"]
    migration = MIGRATION.read_text()

    assert contract["info"]["version"] == "1.0.0"
    assert {"EventReservationPlan", "EventCapacityReservation", "EventResourceVector"} <= set(schemas)
    assert "UNIQUE (event_id, cohort_id, lab_ref)" in migration
    assert "CHECK (status IN ('held', 'released', 'expired'))" in migration
    assert "expires_at" in migration and "TIMESTAMPTZ NOT NULL" in migration


def test_postgres_store_locks_cluster_before_reading_and_writing(monkeypatch):
    class FakeCursor:
        rowcount = 0

        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params=None):
            self.statements.append((" ".join(statement.split()), params))

        def fetchall(self):
            return []

    class FakeConnection:
        def __init__(self):
            self.cursor_value = FakeCursor()
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

    connection = FakeConnection()
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)
    supply = _supply()

    result = PostgresEventReservationStore().reserve(
        _plan("event-a", supply), supply, now=NOW
    )

    statements = [item[0] for item in connection.cursor_value.statements]
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
    lock_index = next(
        index for index, sql in enumerate(statements) if "pg_advisory_xact_lock" in sql
    )
    active_read_index = next(
        index
        for index, sql in enumerate(statements)
        if "cluster_ref = ANY" in sql
    )
    first_insert_index = next(
        index
        for index, sql in enumerate(statements)
        if sql.startswith("INSERT INTO event_capacity_reservations")
    )
    assert lock_index < active_read_index < first_insert_index
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed is True
    assert len(result) == 2


def _reserve_outcome(ledger, plan, supply) -> str:
    try:
        ledger.reserve(plan, supply, now=NOW)
        return "reserved"
    except EventReservationUnavailableError:
        return "unavailable"
