"""Executable local participant journeys for bounded event certification."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from app.domain.enums import SessionStatus, WorkshopStatus
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
from app.services.lifecycle_worker import LifecycleQueueService, LifecycleWorker
from app.services.provisioning import ProvisioningService
from app.services.public_access import PublicAccessService
from app.storage.lifecycle_jobs import InMemoryLifecycleJobStore

from backend.tests.test_event_orchestration import _catalog


def _journey_services(seats: int):
    now = datetime.now(UTC)
    event_id = f"participant-journey-{seats}"
    manifest = EventManifest.model_validate(
        {
            "event_id": event_id,
            "name": f"Participant journey {seats}",
            "owner": "event-owner",
            "technical_approver": "technical-owner",
            "exposure_policy": "public_code",
            "placement_policy": "single_cluster_per_workshop",
            "cohorts": [
                {
                    "cohort_id": "wave-1",
                    "participants": seats,
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
            "retention": {"hours": 4, "starts_from": "cohort_start"},
            "approval": {
                "event_owner_approved": True,
                "technical_approver_approved": True,
                "approved_seat_environments": seats,
                "approved_retention_hours": 4,
            },
        }
    )
    per_seat = EventResourceVector(
        seats=1,
        cpu_millicores=1_000,
        memory_mib=2_000,
        pods=3,
        storage_gib=10,
        routes=3,
        model_slots=1,
    )
    supply = EventCapacitySupply(
        matrix_id=f"journey-matrix-{seats}",
        matrix_digest="sha256:" + "a" * 64,
        fleet_snapshot_id="sha256:" + "b" * 64,
        fleet_observed_at=now,
        clusters=[
            EventClusterCapacity(
                cluster_id="arena",
                enabled=True,
                exposure_policies=["public_code"],
                capabilities=["cpu", "model-endpoint"],
                certified_seats=seats,
                resource_capacity=per_seat.scaled(seats),
                catalogs=[
                    EventCatalogCapacity(
                        catalog_id="build-agent",
                        catalog_release="v2",
                        certified_seats=seats,
                        resources_per_seat=per_seat,
                    )
                ],
            )
        ],
    )
    record = EventRecord(
        manifest=manifest,
        capacity_preview=calculate_event_capacity(manifest, supply),
        created_at=now,
    )
    plan = build_event_reservation_plan(
        record,
        supply,
        expires_at=now + timedelta(hours=4),
        now=now,
    )
    ledger = EventReservationLedger()
    ledger.reserve(plan, supply, now=now)
    provisioning = ProvisioningService(
        catalog=_catalog(),
        event_reservation_ledger=ledger,
    )
    access = PublicAccessService(
        enabled=True,
        shared_origin="https://labs.example.io",
        shared_path_mode=True,
    )
    provisioning.public_access_service = access
    jobs = InMemoryLifecycleJobStore()
    orchestration = EventOrchestrationService(
        reservation_ledger=ledger,
        provisioning=provisioning,
        lifecycle_queue=LifecycleQueueService(jobs),
        public_access=access,
    )
    return record, ledger, provisioning, access, jobs, orchestration


@pytest.mark.parametrize("seats", [1, 5])
def test_event_participant_journey_claims_uses_and_reclaims_every_seat(seats):
    record, ledger, provisioning, access, jobs, orchestration = (
        _journey_services(seats)
    )
    with patch.object(
        provisioning,
        "check_workshop_capacity",
        return_value=(True, "reserved event capacity"),
    ):
        launched = orchestration.launch(
            record,
            EventWorkshopLaunchRequest(tenant_id="event-tenant", ttl="4h"),
        )
        worker = LifecycleWorker(
            store=jobs,
            provisioning_service=provisioning,
            worker_id=f"journey-worker-{seats}",
            lease_seconds=10,
            heartbeat_interval_seconds=1,
        )
        assert worker.run_once() == "succeeded"

    workshop_id = launched.workshops[0].workshop_id
    workshop = provisioning.get_workshop(workshop_id)
    assert workshop.status == WorkshopStatus.READY
    assert len(workshop.session_ids) == seats
    assert {
        provisioning.get_session(session_id).status
        for session_id in workshop.session_ids
    } == {SessionStatus.READY}

    activated = orchestration.activate_public_access(record, workshop_id)
    with ThreadPoolExecutor(max_workers=seats) as pool:
        claims = list(
            pool.map(
                lambda participant: access.claim(
                    workshop_id,
                    f"participant-{participant}@example.test",
                    activated.one_time_access_code,
                    f"192.0.2.{participant}",
                ),
                range(1, seats + 1),
            )
        )
    assert len({item.entitlement.seat_ref for item in claims}) == seats
    for claim in claims:
        validated = access.validate_session(claim.session_token, workshop_id)
        assert validated.participant_id == claim.identity.participant_id

    queued = orchestration.reclaim(record)
    assert queued.status == "queued"
    assert worker.run_once() == "succeeded"
    assert provisioning.get_workshop(workshop_id).status == WorkshopStatus.COMPLETED
    for claim in claims:
        with pytest.raises(ValueError, match="Access denied"):
            access.validate_session(claim.session_token, workshop_id)

    zero_residue = {
        "namespace": 0,
        "image_puller_role_binding": 0,
        "showroom_application": 0,
        "workload_application": 0,
        "credentials": 0,
        "model_key_revocation": 0,
    }
    with patch.object(
        provisioning,
        "inspect_session_cleanup",
        return_value=zero_residue,
    ):
        finalized = orchestration.finalize_cleanup(record)
    assert finalized.cleanup_verified is True
    assert finalized.summary.seats == seats
    assert finalized.summary.external_residue == 0
    assert finalized.summary.access_residue == 0
    assert {
        item.status for item in ledger.list_for_event(record.manifest.event_id)
    } == {"released"}
