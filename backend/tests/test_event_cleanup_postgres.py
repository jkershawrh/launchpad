"""PostgreSQL restart proof for event cleanup finalization."""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.domain.events import (
    EventCapacitySupply,
    EventCatalogCapacity,
    EventClusterCapacity,
    EventManifest,
    EventRecord,
    EventResourceVector,
    EventWorkshopLaunchRequest,
    calculate_event_capacity,
)
from app.services.event_orchestration import EventOrchestrationService
from app.services.event_reservations import (
    EventReservationLedger,
    build_event_reservation_plan,
)
from app.services.events import EventManifestStore
from app.services.lifecycle_worker import LifecycleQueueService, LifecycleWorker
from app.services.provisioning import ProvisioningService
from app.services.public_access import PublicAccessService
from app.storage import database
from app.storage.lifecycle_jobs import PostgresLifecycleJobStore
from app.storage.stores import (
    PostgresAccessStore,
    PostgresEventReservationStore,
    PostgresEventStore,
    PostgresSessionStore,
    PostgresWorkshopStore,
)

from backend.tests.test_event_orchestration import _catalog, _make_ready

TEST_DATABASE_URL = os.environ.get("EVENT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="EVENT_TEST_DATABASE_URL is not configured",
)


@pytest.fixture(autouse=True)
def event_schema(monkeypatch):
    import psycopg2

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL or "")
    database._initialize_database(psycopg2, TEST_DATABASE_URL)
    conn = psycopg2.connect(TEST_DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(
            """TRUNCATE event_capacity_reservations, event_manifests,
                       lifecycle_jobs, lifecycle_aggregate_leases,
                       workshops, lab_sessions, access_policies,
                       participant_identities, participant_entitlements,
                       access_sessions, access_claim_failures,
                       access_audit_events CASCADE"""
        )
    conn.commit()
    conn.close()
    yield


def _event(now: datetime) -> tuple[EventRecord, EventCapacitySupply]:
    manifest = EventManifest.model_validate(
        {
            "event_id": "restart-proof",
            "name": "Restart proof",
            "owner": "event-owner",
            "technical_approver": "technical-owner",
            "exposure_policy": "public_code",
            "placement_policy": "single_cluster_per_workshop",
            "cohorts": [
                {
                    "cohort_id": "wave-1",
                    "participants": 2,
                    "lab_refs": ["agent"],
                }
            ],
            "labs": [
                {
                    "lab_ref": "agent",
                    "catalog_id": "build-agent",
                    "catalog_release": "v2",
                    "required_capabilities": ["cpu", "model-endpoint"],
                }
            ],
            "retention": {"hours": 8, "starts_from": "cohort_start"},
            "approval": {
                "event_owner_approved": True,
                "technical_approver_approved": True,
                "approved_seat_environments": 2,
                "approved_retention_hours": 8,
            },
        }
    )
    supply = EventCapacitySupply(
        matrix_id="restart-matrix-v1",
        matrix_digest="sha256:" + "a" * 64,
        fleet_snapshot_id="sha256:" + "b" * 64,
        fleet_observed_at=now,
        clusters=[
            EventClusterCapacity(
                cluster_id="arena",
                enabled=True,
                exposure_policies=["public_code"],
                capabilities=["cpu", "model-endpoint"],
                certified_seats=2,
                resource_capacity=EventResourceVector(
                    seats=2,
                    cpu_millicores=2_000,
                    memory_mib=4_000,
                    pods=6,
                    storage_gib=20,
                    routes=6,
                    model_slots=2,
                ),
                catalogs=[
                    EventCatalogCapacity(
                        catalog_id="build-agent",
                        catalog_release="v2",
                        certified_seats=2,
                        resources_per_seat=EventResourceVector(
                            seats=1,
                            cpu_millicores=1_000,
                            memory_mib=2_000,
                            pods=3,
                            storage_gib=10,
                            routes=3,
                            model_slots=1,
                        ),
                    )
                ],
            )
        ],
    )
    return EventRecord(
        manifest=manifest,
        capacity_preview=calculate_event_capacity(manifest, supply),
        created_at=now,
    ), supply


def _services():
    stores = SimpleNamespace(
        workshops=PostgresWorkshopStore(),
        sessions=PostgresSessionStore(),
    )
    ledger = EventReservationLedger(db_store=PostgresEventReservationStore())
    provisioning = ProvisioningService(
        catalog=_catalog(),
        db_stores=stores,
        event_reservation_ledger=ledger,
    )
    access = PublicAccessService(
        store=PostgresAccessStore(),
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    provisioning.public_access_service = access
    jobs = PostgresLifecycleJobStore()
    orchestration = EventOrchestrationService(
        reservation_ledger=ledger,
        provisioning=provisioning,
        lifecycle_queue=LifecycleQueueService(jobs),
        public_access=access,
    )
    return ledger, provisioning, access, jobs, orchestration


def _prepare_reclaimed_event() -> EventRecord:
    now = datetime.now(UTC)
    record, supply = _event(now)
    EventManifestStore(db_store=PostgresEventStore()).create(record)
    ledger, provisioning, access, jobs, orchestration = _services()
    plan = build_event_reservation_plan(
        record,
        supply,
        expires_at=now + timedelta(hours=8),
        now=now,
    )
    ledger.reserve(plan, supply, now=now)

    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record,
            request=EventWorkshopLaunchRequest(
                tenant_id="event-tenant",
                ttl="8h",
            ),
        )
    workshop_id = launched.workshops[0].workshop_id
    _make_ready(provisioning, workshop_id)
    activated = orchestration.activate_public_access(record, workshop_id)
    access.claim(
        order_id=workshop_id,
        email="participant@example.test",
        code=activated.one_time_access_code,
        ip_address="192.0.2.10",
    )
    orchestration.reclaim(record)
    worker = LifecycleWorker(
        store=jobs,
        provisioning_service=provisioning,
        worker_id="before-restart",
        lease_seconds=10,
        heartbeat_interval_seconds=1,
    )
    assert worker.run_once() == "succeeded"
    return record


def test_cleanup_finalization_survives_two_process_restarts() -> None:
    record = _prepare_reclaimed_event()

    restarted_record = EventManifestStore(db_store=PostgresEventStore()).get(
        record.manifest.event_id
    )
    assert restarted_record is not None
    _, _, _, _, restarted = _services()
    finalized = restarted.finalize_cleanup(restarted_record)

    _, _, _, _, restarted_again = _services()
    repeated = restarted_again.finalize_cleanup(restarted_record)

    assert finalized.cleanup_verified is True
    assert finalized.released_reservations == 1
    assert finalized.summary.seats == 2
    assert finalized.summary.sessions == 2
    assert finalized.summary.external_residue == 0
    assert finalized.summary.access_residue == 0
    assert repeated.released_reservations == 0
    assert repeated.cleanup_evidence_id == finalized.cleanup_evidence_id
    persisted = EventReservationLedger(
        db_store=PostgresEventReservationStore()
    ).list_for_event(record.manifest.event_id)
    assert {item.status for item in persisted} == {"released"}
    assert {item.cleanup_evidence_id for item in persisted} == {
        finalized.cleanup_evidence_id
    }


def test_concurrent_restarted_finalizers_converge_on_one_release() -> None:
    record = _prepare_reclaimed_event()
    barrier = threading.Barrier(3)
    results = []
    errors = []

    def finalize() -> None:
        try:
            restarted_record = EventManifestStore(
                db_store=PostgresEventStore()
            ).get(record.manifest.event_id)
            assert restarted_record is not None
            _, _, _, _, restarted = _services()
            barrier.wait()
            results.append(restarted.finalize_cleanup(restarted_record))
        except Exception as exc:  # noqa: BLE001 - preserve thread failures
            errors.append(exc)

    first = threading.Thread(target=finalize)
    second = threading.Thread(target=finalize)
    first.start()
    second.start()
    barrier.wait()
    first.join(timeout=10)
    second.join(timeout=10)

    assert errors == []
    assert len(results) == 2
    assert sorted(item.released_reservations for item in results) == [0, 1]
    assert len({item.cleanup_evidence_id for item in results}) == 1
    persisted = EventReservationLedger(
        db_store=PostgresEventReservationStore()
    ).list_for_event(record.manifest.event_id)
    assert {item.status for item in persisted} == {"released"}
    assert {item.cleanup_evidence_id for item in persisted} == {
        results[0].cleanup_evidence_id
    }
