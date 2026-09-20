"""Executable local participant journeys for bounded event certification."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from app.api import deps
from app.api.routers import public_access as public_access_router
from app.auth.oauth import User, get_current_user
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
from app.main import app
from app.services.event_orchestration import EventOrchestrationService
from app.services.event_reservations import (
    EventReservationLedger,
    build_event_reservation_plan,
)
from app.services.events import EventManifestStore
from app.services.lifecycle_worker import LifecycleQueueService, LifecycleWorker
from app.services.provisioning import ProvisioningService
from app.services.public_access import PublicAccessService
from app.storage.lifecycle_jobs import InMemoryLifecycleJobStore
from fastapi.testclient import TestClient

from backend.tests.test_event_orchestration import _catalog


def _journey_services(seats: int, *, reserve: bool = True):
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
    if reserve:
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
    return record, supply, ledger, provisioning, access, jobs, orchestration


@pytest.mark.parametrize("seats", [1, 5, 25, 30])
def test_event_participant_journey_claims_uses_and_reclaims_every_seat(seats):
    record, _supply, ledger, provisioning, access, jobs, orchestration = (
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


@pytest.mark.parametrize("seats", [1, 5, 25, 30])
def test_http_contract_drives_exact_participant_journey(seats, monkeypatch):
    (
        record,
        supply,
        ledger,
        provisioning,
        access,
        jobs,
        orchestration,
    ) = _journey_services(seats, reserve=False)
    event_store = EventManifestStore()
    event_store.create(record)
    app.dependency_overrides[deps.get_event_capacity_supply] = lambda: supply
    app.dependency_overrides[deps.get_event_manifest_store] = lambda: event_store
    app.dependency_overrides[deps.get_event_reservation_ledger] = lambda: ledger
    app.dependency_overrides[deps.get_event_orchestration_service] = (
        lambda: orchestration
    )
    app.dependency_overrides[get_current_user] = lambda: User(
        username="event-admin",
        is_admin=True,
    )
    monkeypatch.setattr(public_access_router, "public_access_service", access)
    monkeypatch.setattr(
        public_access_router,
        "provisioning_service",
        provisioning,
    )
    monkeypatch.setattr(
        provisioning,
        "bind_public_participant",
        lambda *_args, **_kwargs: None,
    )

    event_id = record.manifest.event_id
    client = TestClient(app)
    try:
        reserved = client.post(
            f"/api/v1/events/{event_id}/reservations",
            json={
                "expires_at": (
                    datetime.now(UTC) + timedelta(hours=4)
                ).isoformat()
            },
        )
        assert reserved.status_code == 201
        with patch.object(
            provisioning,
            "check_workshop_capacity",
            return_value=(True, "reserved event capacity"),
        ):
            launched = client.post(
                f"/api/v1/events/{event_id}/workshops/launch",
                json={"tenant_id": "event-tenant", "ttl": "4h"},
            )
            assert launched.status_code == 202
            worker = LifecycleWorker(
                store=jobs,
                provisioning_service=provisioning,
                worker_id=f"http-journey-{seats}",
                lease_seconds=10,
                heartbeat_interval_seconds=1,
            )
            assert worker.run_once() == "succeeded"

        workshop_id = launched.json()["workshops"][0]["workshop_id"]
        activated = client.post(
            f"/api/v1/events/{event_id}/workshops/{workshop_id}/public-access"
        )
        assert activated.status_code == 201
        code = activated.json()["one_time_access_code"]

        def claim_and_authorize(participant: int):
            participant_client = TestClient(
                app,
                base_url="https://testserver",
            )
            claimed = participant_client.post(
                "/api/v1/public-access/claim",
                json={
                    "order_id": workshop_id,
                    "email": f"participant-{participant}@example.test",
                    "code": code,
                },
            )
            assert claimed.status_code == 200
            assert "session_token" not in claimed.json()
            token = claimed.cookies.get("launchpad_access")
            assert token
            authorized = participant_client.get(
                f"/api/v1/public-access/authorize/{workshop_id}"
            )
            assert authorized.status_code == 200
            return claimed.json(), authorized.json(), token

        with ThreadPoolExecutor(max_workers=seats) as pool:
            participants = list(
                pool.map(claim_and_authorize, range(1, seats + 1))
            )
        assert len({item[0]["seat_ref"] for item in participants}) == seats
        assert {item[1]["authorized"] for item in participants} == {True}

        status = client.get(f"/api/v1/events/{event_id}/status")
        assert status.status_code == 200
        assert status.json()["summary"]["public_workshops_active"] == 1

        reclaimed = client.post(f"/api/v1/events/{event_id}/reclaim")
        assert reclaimed.status_code == 202
        assert worker.run_once() == "succeeded"
        for _, _, token in participants:
            denied_client = TestClient(app, base_url="https://testserver")
            denied_client.cookies.set("launchpad_access", token)
            denied = denied_client.get(
                f"/api/v1/public-access/authorize/{workshop_id}"
            )
            assert denied.status_code == 403

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
            finalized = client.post(
                f"/api/v1/events/{event_id}/reclaim/finalize"
            )
        assert finalized.status_code == 200
        assert finalized.json()["cleanup_verified"] is True
        assert finalized.json()["summary"]["seats"] == seats
        assert finalized.json()["released_reservations"] == 1
    finally:
        for dependency in (
            deps.get_event_capacity_supply,
            deps.get_event_manifest_store,
            deps.get_event_reservation_ledger,
            deps.get_event_orchestration_service,
            get_current_user,
        ):
            app.dependency_overrides.pop(dependency, None)
