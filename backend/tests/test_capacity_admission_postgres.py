"""Disposable-PostgreSQL proofs for whole-workshop capacity admission."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.domain.capacity_admission import (
    CapacitySupplySnapshot,
    InferenceCapacity,
    WorkshopCapacityRequest,
)
from app.domain.events import EventResourceVector
from app.services.capacity_admission import (
    AdmissionIdempotencyConflict,
    AdmissionReleaseConflict,
)
from app.storage import database
from app.storage.capacity_admission import PostgresCapacityAdmissionStore

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
TEST_DATABASE_URL = os.environ.get("EVENT_TEST_DATABASE_URL")
MIGRATION = Path(__file__).parents[1] / "migrations/009_capacity_admission.sql"


def _supply(*, seats: int = 30) -> CapacitySupplySnapshot:
    return CapacitySupplySnapshot(
        snapshot_id="sha256:" + "a" * 64,
        policy_id="capacity-policy-v1",
        cluster_ref="arena",
        catalog_id="serve-llms",
        catalog_release="release-v1",
        eligible=True,
        infrastructure=EventResourceVector(
            seats=seats,
            cpu_millicores=seats * 1000,
            memory_mib=seats * 2048,
            pods=seats * 3,
            storage_gib=seats * 10,
            routes=seats * 3,
            model_slots=seats,
        ),
        inference=InferenceCapacity(
            model_id="granite-tools",
            model_release="granite-3.2-8b-tools-v1",
            concurrent_requests=seats,
            input_tokens_per_minute=seats * 1000,
            output_tokens_per_minute=seats * 500,
        ),
        observed_at=NOW,
        valid_until=NOW + timedelta(minutes=2),
    )


def _request(
    workshop_id: str,
    *,
    seats: int = 20,
    idempotency_key: str | None = None,
) -> WorkshopCapacityRequest:
    return WorkshopCapacityRequest(
        request_id=f"request-{workshop_id}",
        idempotency_key=idempotency_key or f"admit-{workshop_id}",
        forecast_ref="forecast:event-1:v1",
        event_id="event-1",
        workshop_id=workshop_id,
        catalog_id="serve-llms",
        catalog_release="release-v1",
        cluster_ref="arena",
        seats=seats,
        infrastructure_per_seat=EventResourceVector(
            seats=1,
            cpu_millicores=1000,
            memory_mib=2048,
            pods=3,
            storage_gib=10,
            routes=3,
            model_slots=1,
        ),
        inference_per_seat=InferenceCapacity(
            model_id="granite-tools",
            model_release="granite-3.2-8b-tools-v1",
            concurrent_requests=1,
            input_tokens_per_minute=1000,
            output_tokens_per_minute=500,
        ),
        requested_at=NOW,
    )


def test_capacity_admission_migration_owns_durable_decision_and_hold_schema():
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS capacity_admission_decisions" in sql
    assert "CREATE TABLE IF NOT EXISTS aggregate_capacity_reservations" in sql
    assert "idempotency_key" in sql
    assert "UNIQUE (workshop_id)" in sql
    assert "CHECK (status IN ('held', 'released'))" in sql
    assert "cleanup_evidence_id" in sql
    assert "WHERE status = 'held'" in sql


requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="EVENT_TEST_DATABASE_URL is not configured",
)


@pytest.fixture(autouse=True)
def admission_schema(monkeypatch):
    if not TEST_DATABASE_URL:
        yield
        return
    import psycopg2

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    database._initialize_database(psycopg2, TEST_DATABASE_URL)
    conn = psycopg2.connect(TEST_DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE aggregate_capacity_reservations, capacity_admission_decisions CASCADE"
        )
    conn.commit()
    conn.close()
    yield


@requires_postgres
def test_independent_stores_serialize_competing_whole_workshops():
    supply = _supply(seats=30)
    stores = [PostgresCapacityAdmissionStore(), PostgresCapacityAdmissionStore()]

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(
            executor.map(
                lambda args: args[0].admit(args[1], supply, now=NOW),
                zip(
                    stores,
                    [_request("workshop-a"), _request("workshop-b")],
                    strict=True,
                ),
            )
        )

    assert sorted(item.status for item in decisions) == ["accepted", "rejected"]
    active = PostgresCapacityAdmissionStore().list_active_reservations()
    assert len(active) == 1
    assert active[0].resources.infrastructure.seats == 20


@requires_postgres
def test_cross_process_idempotency_replays_one_decision_and_rejects_key_reuse():
    supply = _supply()
    request = _request("workshop-a")

    first = PostgresCapacityAdmissionStore().admit(request, supply, now=NOW)
    replay = PostgresCapacityAdmissionStore().admit(
        request, supply, now=NOW + timedelta(seconds=30)
    )

    assert replay == first
    assert len(PostgresCapacityAdmissionStore().list_records()) == 1
    with pytest.raises(AdmissionIdempotencyConflict, match="different request"):
        PostgresCapacityAdmissionStore().admit(
            request.model_copy(update={"seats": 19}), supply, now=NOW
        )


@requires_postgres
def test_concurrent_identical_requests_converge_on_one_decision():
    request = _request("workshop-a")
    supply = _supply()

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(
            executor.map(
                lambda store: store.admit(request, supply, now=NOW),
                [PostgresCapacityAdmissionStore(), PostgresCapacityAdmissionStore()],
            )
        )

    assert decisions[0] == decisions[1]
    assert decisions[0].status == "accepted"
    assert len(PostgresCapacityAdmissionStore().list_records()) == 1
    assert len(PostgresCapacityAdmissionStore().list_active_reservations()) == 1


@requires_postgres
def test_cleanup_evidence_release_is_durable_idempotent_and_frees_capacity():
    supply = _supply(seats=20)
    first_store = PostgresCapacityAdmissionStore()
    accepted = first_store.admit(_request("workshop-a"), supply, now=NOW)
    evidence = "sha256:" + "c" * 64

    released = PostgresCapacityAdmissionStore().release(
        accepted.reservation_id,
        cleanup_evidence_id=evidence,
        now=NOW + timedelta(minutes=1),
    )
    replay = PostgresCapacityAdmissionStore().release(
        accepted.reservation_id,
        cleanup_evidence_id=evidence,
        now=NOW + timedelta(minutes=2),
    )

    assert released.status == "released"
    assert replay == released
    with pytest.raises(AdmissionReleaseConflict, match="different cleanup evidence"):
        PostgresCapacityAdmissionStore().release(
            accepted.reservation_id,
            cleanup_evidence_id="sha256:" + "d" * 64,
            now=NOW + timedelta(minutes=2),
        )
    next_decision = PostgresCapacityAdmissionStore().admit(_request("workshop-b"), supply, now=NOW)
    assert next_decision.status == "accepted"


@requires_postgres
def test_rejected_decision_survives_restart_without_creating_a_hold():
    request = _request("too-large", seats=31)

    rejected = PostgresCapacityAdmissionStore().admit(request, _supply(seats=30), now=NOW)
    replay = PostgresCapacityAdmissionStore().admit(request, _supply(seats=60), now=NOW)

    assert replay == rejected
    assert replay.status == "rejected"
    assert PostgresCapacityAdmissionStore().list_active_reservations() == []
