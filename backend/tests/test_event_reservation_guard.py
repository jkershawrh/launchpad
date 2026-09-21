"""A pure physical-capacity guard runs after active holds are read under lock."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from app.domain.event_inflight_capacity import (
    EventInflightCapacitySnapshot,
    InflightClusterUsage,
    InflightResourceVector,
)
from app.services.event_inflight_capacity import assess_event_inflight_capacity
from app.services.event_reservations import (
    EventReservationLedger,
    EventReservationUnavailableError,
    build_event_reservation_plan,
)
from app.storage import stores
from app.storage.stores import PostgresEventReservationStore

from backend.tests.test_event_reservation_ledger import NOW, _record, _supply


def test_optional_guard_serializes_physical_headroom_across_concurrent_orders():
    supply = _supply(seats=120, cpu_millicores=120_000)
    cluster = supply.clusters[0]
    cluster.resource_capacity.memory_mib = 300_000
    cluster.resource_capacity.pods = 400
    cluster.resource_capacity.storage_gib = 1_200
    cluster.resource_capacity.routes = 400
    cluster.resource_capacity.model_slots = 120
    for catalog in cluster.catalogs:
        catalog.certified_seats = 120
    snapshot = EventInflightCapacitySnapshot(
        snapshot_id="sha256:" + "e" * 64,
        observed_at=NOW,
        clusters=[
            InflightClusterUsage(
                cluster_id="arena",
                accounting_complete=True,
                allocatable=InflightResourceVector(
                    cpu_millicores=90_000,
                    memory_mib=300_000,
                    pods=400,
                    model_slots=120,
                ),
                workloads=[],
            )
        ],
    )
    ledger = EventReservationLedger()

    def guard(requested, active, now):
        cpu = sum(item.resources.cpu_millicores for item in requested)
        result = assess_event_inflight_capacity(
            {"arena": InflightResourceVector(cpu_millicores=cpu)},
            active,
            snapshot,
            now=now,
        )
        if result.status != "available":
            raise EventReservationUnavailableError(result.explanation)

    def reserve(event_id):
        record = _record(event_id, supply)
        plan = build_event_reservation_plan(
            record, supply, expires_at=NOW + timedelta(hours=1), now=NOW
        )
        try:
            return ledger.reserve(plan, supply, now=NOW, guard=guard)
        except EventReservationUnavailableError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, ["event-a", "event-b"]))

    assert sorted(item is not None for item in outcomes) == [False, True]
    assert len(ledger.snapshot_active()) == 2


def test_postgres_guard_runs_after_locked_active_read_and_before_any_insert(monkeypatch):
    class Cursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=None):
            self.statements.append(" ".join(statement.split()))

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.current = Cursor()
            self.rollbacks = 0
            self.commits = 0

        def cursor(self):
            return self.current

        def rollback(self):
            self.rollbacks += 1

        def commit(self):
            self.commits += 1

        def close(self):
            pass

    connection = Connection()
    monkeypatch.setattr(stores, "_get_sync_conn", lambda: connection)
    supply = _supply()
    plan = build_event_reservation_plan(
        _record("event-a", supply),
        supply,
        expires_at=NOW + timedelta(hours=1),
        now=NOW,
    )

    def guard(requested, active, now):
        assert requested == plan.reservations
        assert active == []
        assert now == NOW
        sql = connection.current.statements
        assert any("pg_advisory_xact_lock" in statement for statement in sql)
        assert any("FOR UPDATE" in statement for statement in sql)
        assert not any("INSERT INTO event_capacity_reservations" in statement for statement in sql)
        raise EventReservationUnavailableError("physical headroom unavailable")

    with pytest.raises(EventReservationUnavailableError, match="physical headroom"):
        PostgresEventReservationStore().reserve(plan, supply, now=NOW, guard=guard)
    assert connection.commits == 0
    assert connection.rollbacks == 1
