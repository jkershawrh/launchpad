from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from app.domain.enums import (
    CatalogCategory,
    CatalogStatus,
    SessionStatus,
    WorkshopSeatStatus,
    WorkshopStatus,
)
from app.domain.events import EventWorkshopLaunchRequest
from app.domain.lifecycle_jobs import LifecycleJobOperation
from app.domain.models import CatalogItem, LabSession
from app.services.event_orchestration import (
    EventOrchestrationConflictError,
    EventOrchestrationService,
)
from app.services.event_reservations import EventReservationLedger
from app.services.lifecycle_worker import LifecycleQueueService, LifecycleWorker
from app.services.provisioning import ProvisioningService
from app.services.public_access import PublicAccessService
from app.storage.lifecycle_jobs import InMemoryLifecycleJobStore

from backend.tests.test_event_reservation_ledger import NOW, _plan, _record, _supply

CONTRACT = Path(__file__).parents[2] / "contracts" / "event-orchestration-v1.yaml"


def test_event_orchestration_contract_keeps_public_access_pending():
    contract = yaml.safe_load(CONTRACT.read_text())
    operation = contract["paths"][
        "/api/v1/events/{event_id}/workshops/launch"
    ]["post"]
    result = contract["components"]["schemas"]["EventWorkshopLaunchResult"]

    assert contract["info"]["version"] == "1.4.0"
    assert operation["responses"]["202"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/EventWorkshopLaunchResult"}
    assert result["properties"]["public_access_state"]["enum"] == [
        "not_required",
        "pending_activation",
    ]
    assert (
        contract["paths"][
            "/api/v1/events/{event_id}/workshops/{workshop_id}/public-access"
        ]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/EventWorkshopPublicAccessResult"}
    )
    assert (
        contract["paths"]["/api/v1/events/{event_id}/status"]["get"]
        ["responses"]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/EventStatusResult"}
    )
    status = contract["components"]["schemas"]["EventStatusResult"]
    assert "one_time_access_code" not in str(status)
    assert (
        contract["paths"]["/api/v1/events/{event_id}/reclaim"]["post"]
        ["responses"]["202"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/EventWorkshopReclaimResult"}
    )
    assert (
        contract["paths"]["/api/v1/events/{event_id}/reclaim/finalize"]
        ["post"]["responses"]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/EventCleanupEvidenceResult"}
    )
    cleanup = contract["components"]["schemas"]["EventCleanupEvidenceResult"]
    assert "one_time_access_code" not in str(cleanup)
    assert "email" not in str(cleanup)


def _catalog():
    releases = {"serve-llms": "v1", "build-agent": "v2"}

    def get_item(catalog_id: str):
        version = releases.get(catalog_id)
        if version is None:
            return None
        return CatalogItem(
            catalog_item_id=catalog_id,
            display_name=catalog_id,
            category=CatalogCategory.GUIDED_BUILD,
            version=version,
            status=CatalogStatus.ACTIVE,
            default_hardware_profile="xeon-basic",
            default_quota_profile="standard",
            metadata={
                "max_workshop_seats": 30,
                "allowed_exposure_policies": ["public_code", "internal"],
            },
        )

    return SimpleNamespace(get_item=get_item)


def _services():
    supply = _supply()
    record = _record("event-a", supply)
    plan = _plan("event-a", supply)
    expires_at = max(NOW, datetime.now(UTC)) + timedelta(hours=8)
    plan = plan.model_copy(
        update={
            "expires_at": expires_at,
            "reservations": [
                item.model_copy(update={"expires_at": expires_at})
                for item in plan.reservations
            ],
        }
    )
    ledger = EventReservationLedger()
    ledger.reserve(plan, supply, now=NOW)
    provisioning = ProvisioningService(
        catalog=_catalog(), event_reservation_ledger=ledger
    )
    jobs = InMemoryLifecycleJobStore()
    orchestration = EventOrchestrationService(
        reservation_ledger=ledger,
        provisioning=provisioning,
        lifecycle_queue=LifecycleQueueService(jobs),
    )
    return record, ledger, provisioning, jobs, orchestration


def _make_ready(provisioning, workshop_id: str):
    workshop = provisioning.get_workshop(workshop_id)
    expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=4)
    seats = []
    for seat in workshop.seats:
        session = LabSession(
            request_id=f"request-{seat.seat_number}",
            tenant_id=workshop.tenant_id,
            catalog_item_id=workshop.catalog_item_id,
            cluster_ref=workshop.cluster_ref,
            status=SessionStatus.READY,
            expires_at=expires,
        )
        provisioning._save_session(session)
        seats.append(
            seat.model_copy(
                update={
                    "status": WorkshopSeatStatus.READY,
                    "session_id": session.session_id,
                }
            )
        )
    ready = workshop.model_copy(
        update={
            "status": WorkshopStatus.READY,
            "seats": seats,
            "session_ids": [seat.session_id for seat in seats],
        }
    )
    provisioning._save_workshop(ready)
    return ready, expires


def test_launch_queues_every_reserved_workshop_on_its_persisted_cluster():
    record, ledger, provisioning, jobs, orchestration = _services()

    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        result = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )

    assert result.status == "queued"
    assert result.public_access_state == "pending_activation"
    assert len(result.workshops) == 2
    assert len(jobs.list_all()) == 2
    assert {item.cluster_ref for item in result.workshops} == {"arena"}
    assert {item.seats for item in result.workshops} == {30}
    assert {
        provisioning.get_workshop(item.workshop_id).status
        for item in result.workshops
    } == {WorkshopStatus.QUEUED}
    assert {
        item.status for item in ledger.list_for_event("event-a", now=NOW)
    } == {"consumed"}


def test_launch_is_idempotent_and_does_not_duplicate_lifecycle_jobs():
    record, _ledger, provisioning, jobs, orchestration = _services()

    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        first = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
        repeated = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )

    assert repeated == first
    assert len(jobs.list_all()) == 2
    assert len(provisioning.list_workshops()) == 2


def test_partial_queue_failure_can_be_retried_without_duplicate_workshops():
    record, _ledger, provisioning, jobs, orchestration = _services()
    original_enqueue = orchestration.lifecycle_queue.enqueue_workshop_provision
    attempts = 0

    def fail_second_once(workshop):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("queue unavailable")
        return original_enqueue(workshop)

    with (
        patch.object(
            provisioning, "check_workshop_capacity", return_value=(True, "ok")
        ),
        patch.object(
            orchestration.lifecycle_queue,
            "enqueue_workshop_provision",
            side_effect=fail_second_once,
        ),
        pytest.raises(RuntimeError, match="queue unavailable"),
    ):
        orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )

    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        recovered = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )

    assert recovered.status == "queued"
    assert len(provisioning.list_workshops()) == 2
    assert len(jobs.list_all()) == 2


def test_launch_fails_closed_when_event_reservations_are_incomplete():
    record, ledger, _provisioning, _jobs, orchestration = _services()
    reservation = ledger.list_for_event("event-a", now=NOW)[0]
    ledger._records.pop(reservation.reservation_id)

    with pytest.raises(EventOrchestrationConflictError, match="complete reservation"):
        orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )


def test_public_access_activation_waits_for_complete_workshop_readiness():
    record, _ledger, provisioning, _jobs, orchestration = _services()
    access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    orchestration.public_access = access
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )

    with pytest.raises(EventOrchestrationConflictError, match="not fully ready"):
        orchestration.activate_public_access(
            record, launched.workshops[0].workshop_id
        )


def test_public_access_activation_returns_code_once_after_readiness():
    record, _ledger, provisioning, _jobs, orchestration = _services()
    access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    orchestration.public_access = access
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    workshop_id = launched.workshops[0].workshop_id
    ready, expires = _make_ready(provisioning, workshop_id)

    activated = orchestration.activate_public_access(record, workshop_id)

    assert activated.workshop_id == workshop_id
    assert activated.public_url.startswith("https://labs.example.io/labs/")
    assert activated.one_time_access_code
    assert activated.expires_at == expires
    policy = access.get_policy(workshop_id)
    assert policy.seat_refs == [seat.seat_id for seat in ready.seats]
    saved = provisioning.get_workshop(workshop_id)
    assert saved.public_url == activated.public_url
    assert saved.metadata["public_access_state"] == "active"

    with pytest.raises(EventOrchestrationConflictError, match="already activated"):
        orchestration.activate_public_access(record, workshop_id)


def test_public_access_activation_rejects_released_capacity_binding():
    record, ledger, provisioning, _jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    workshop_id = launched.workshops[0].workshop_id
    _make_ready(provisioning, workshop_id)
    ledger.release(
        record.manifest.event_id,
        cleanup_evidence_id="evidence:cleanup:event-a",
    )

    with pytest.raises(
        EventOrchestrationConflictError,
        match="consumed event reservation",
    ):
        orchestration.activate_public_access(record, workshop_id)


def test_event_status_reconciles_reservations_jobs_seats_and_public_access():
    record, _ledger, provisioning, _jobs, orchestration = _services()

    reserved = orchestration.status(record)
    assert reserved.state == "reserved"
    assert reserved.summary.reservations == 2
    assert reserved.summary.workshops == 0
    assert reserved.reservation_complete is True

    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    progressing = orchestration.status(record)
    assert progressing.state == "progressing"
    assert progressing.summary.lifecycle_jobs == 2
    assert progressing.summary.ready_seats == 0

    for item in launched.workshops:
        _make_ready(provisioning, item.workshop_id)
    waiting = orchestration.status(record)
    assert waiting.state == "awaiting_public_access"
    assert waiting.summary.ready_seats == 60

    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    for item in launched.workshops:
        orchestration.activate_public_access(record, item.workshop_id)
    ready = orchestration.status(record)
    assert ready.state == "ready"
    assert ready.summary.public_workshops_active == 2
    assert all(item.public_access_state == "active" for item in ready.workshops)
    assert "one_time_access_code" not in ready.model_dump_json()


def test_event_status_surfaces_incomplete_reservation_plan_without_mutation():
    record, ledger, _provisioning, _jobs, orchestration = _services()
    reservation = ledger.list_for_event("event-a", now=NOW)[0]
    ledger._records.pop(reservation.reservation_id)

    status = orchestration.status(record)

    assert status.state == "attention_required"
    assert status.reservation_complete is False
    assert status.summary.reservations == 1


def test_event_status_surfaces_expired_capacity_as_attention_required():
    record, ledger, _provisioning, _jobs, orchestration = _services()
    reservation = ledger.list_for_event("event-a", now=NOW)[0]
    ledger._records[reservation.reservation_id] = reservation.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )

    status = orchestration.status(record)

    assert status.state == "attention_required"
    assert status.reservation_complete is True
    assert status.workshops[0].reservation_status == "expired"


def test_event_reclaim_disables_access_before_cluster_bound_cleanup():
    record, _ledger, provisioning, jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    for item in launched.workshops:
        _make_ready(provisioning, item.workshop_id)
        orchestration.activate_public_access(record, item.workshop_id)

    reclaimed = orchestration.reclaim(record)
    repeated = orchestration.reclaim(record)

    assert reclaimed == repeated
    assert reclaimed.status == "queued"
    assert len(reclaimed.workshops) == 2
    assert {item.cluster_ref for item in reclaimed.workshops} == {"arena"}
    assert {item.public_access_state for item in reclaimed.workshops} == {"disabled"}
    assert all(
        not orchestration.public_access.get_policy(item.workshop_id).enabled
        for item in reclaimed.workshops
    )
    assert {
        provisioning.get_workshop(item.workshop_id).status
        for item in reclaimed.workshops
    } == {WorkshopStatus.RECLAIMING}
    reclaim_jobs = [
        job
        for job in jobs.list_all()
        if job.operation == LifecycleJobOperation.RECLAIM_WORKSHOP
    ]
    assert len(reclaim_jobs) == 2
    assert {job.cluster_ref for job in reclaim_jobs} == {"arena"}


def test_event_reclaim_fails_before_disabling_access_for_incomplete_plan():
    record, ledger, provisioning, _jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    first = launched.workshops[0]
    _make_ready(provisioning, first.workshop_id)
    orchestration.activate_public_access(record, first.workshop_id)
    missing = ledger.list_for_event(record.manifest.event_id, now=NOW)[1]
    ledger._records.pop(missing.reservation_id)

    with pytest.raises(EventOrchestrationConflictError, match="complete reservation"):
        orchestration.reclaim(record)

    assert orchestration.public_access.get_policy(first.workshop_id).enabled is True


def test_partial_event_reclaim_queue_failure_recovers_without_duplicate_jobs():
    record, _ledger, provisioning, jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    for item in launched.workshops:
        _make_ready(provisioning, item.workshop_id)
        orchestration.activate_public_access(record, item.workshop_id)

    original_enqueue = orchestration.lifecycle_queue.enqueue_workshop_reclaim
    attempts = 0

    def fail_second_once(workshop):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("queue unavailable")
        return original_enqueue(workshop)

    with (
        patch.object(
            orchestration.lifecycle_queue,
            "enqueue_workshop_reclaim",
            side_effect=fail_second_once,
        ),
        pytest.raises(RuntimeError, match="queue unavailable"),
    ):
        orchestration.reclaim(record)

    assert all(
        not orchestration.public_access.get_policy(item.workshop_id).enabled
        for item in launched.workshops
    )
    recovered = orchestration.reclaim(record)
    reclaim_jobs = [
        job
        for job in jobs.list_all()
        if job.operation == LifecycleJobOperation.RECLAIM_WORKSHOP
    ]
    assert len(recovered.workshops) == 2
    assert len(reclaim_jobs) == 2


def _run_event_reclaim_jobs(provisioning, jobs):
    worker = LifecycleWorker(
        store=jobs,
        provisioning_service=provisioning,
        worker_id="event-cleanup-worker",
        lease_seconds=10,
        heartbeat_interval_seconds=1,
    )
    assert worker.run_once() == "succeeded"
    assert worker.run_once() == "succeeded"


def test_event_cleanup_finalization_releases_capacity_with_stable_evidence():
    record, ledger, provisioning, jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    for item in launched.workshops:
        _make_ready(provisioning, item.workshop_id)
        orchestration.activate_public_access(record, item.workshop_id)
    orchestration.reclaim(record)
    _run_event_reclaim_jobs(provisioning, jobs)

    finalized = orchestration.finalize_cleanup(record)
    repeated = orchestration.finalize_cleanup(record)

    assert finalized.cleanup_verified is True
    assert finalized.cleanup_evidence_id.startswith("sha256:")
    assert finalized.released_reservations == 2
    assert repeated.cleanup_evidence_id == finalized.cleanup_evidence_id
    assert repeated.released_reservations == 0
    assert finalized.summary.workshops == 2
    assert finalized.summary.seats == 60
    assert finalized.summary.sessions == 60
    assert finalized.summary.external_residue == 0
    assert finalized.summary.active_entitlements == 0
    assert {
        item.status
        for item in ledger.list_for_event(record.manifest.event_id, now=NOW)
    } == {"released"}


def test_event_cleanup_finalization_fails_closed_until_jobs_complete():
    record, ledger, provisioning, _jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    for item in launched.workshops:
        _make_ready(provisioning, item.workshop_id)
        orchestration.activate_public_access(record, item.workshop_id)
    orchestration.reclaim(record)

    with pytest.raises(EventOrchestrationConflictError, match="not proven"):
        orchestration.finalize_cleanup(record)

    assert {
        item.status
        for item in ledger.list_for_event(record.manifest.event_id, now=NOW)
    } == {"consumed"}


def test_event_cleanup_finalization_rejects_external_residue():
    record, ledger, provisioning, jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    for item in launched.workshops:
        _make_ready(provisioning, item.workshop_id)
        orchestration.activate_public_access(record, item.workshop_id)
    orchestration.reclaim(record)
    _run_event_reclaim_jobs(provisioning, jobs)

    with (
        patch.object(
            provisioning,
            "inspect_session_cleanup",
            return_value={
                "namespace": 1,
                "image_puller_role_binding": 0,
                "showroom_application": 0,
                "workload_application": 0,
                "credentials": 0,
            },
        ),
        pytest.raises(EventOrchestrationConflictError, match="not proven"),
    ):
        orchestration.finalize_cleanup(record)

    assert {
        item.status
        for item in ledger.list_for_event(record.manifest.event_id, now=NOW)
    } == {"consumed"}


def test_event_cleanup_finalization_fails_closed_when_inspection_errors():
    record, ledger, provisioning, jobs, orchestration = _services()
    orchestration.public_access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    with patch.object(
        provisioning, "check_workshop_capacity", return_value=(True, "ok")
    ):
        launched = orchestration.launch(
            record, EventWorkshopLaunchRequest(tenant_id="event-tenant")
        )
    for item in launched.workshops:
        _make_ready(provisioning, item.workshop_id)
        orchestration.activate_public_access(record, item.workshop_id)
    orchestration.reclaim(record)
    _run_event_reclaim_jobs(provisioning, jobs)

    with (
        patch.object(
            provisioning,
            "inspect_session_cleanup",
            side_effect=RuntimeError("cluster API unavailable"),
        ),
        pytest.raises(EventOrchestrationConflictError, match="not proven"),
    ):
        orchestration.finalize_cleanup(record)

    assert {
        item.status
        for item in ledger.list_for_event(record.manifest.event_id, now=NOW)
    } == {"consumed"}
