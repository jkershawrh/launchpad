from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from app.domain.enums import CatalogCategory, CatalogStatus, WorkshopStatus
from app.domain.events import EventWorkshopLaunchRequest
from app.domain.models import CatalogItem
from app.services.event_orchestration import (
    EventOrchestrationConflictError,
    EventOrchestrationService,
)
from app.services.event_reservations import EventReservationLedger
from app.services.lifecycle_worker import LifecycleQueueService
from app.services.provisioning import ProvisioningService
from app.storage.lifecycle_jobs import InMemoryLifecycleJobStore

from backend.tests.test_event_reservation_ledger import NOW, _plan, _record, _supply

CONTRACT = Path(__file__).parents[2] / "contracts" / "event-orchestration-v1.yaml"


def test_event_orchestration_contract_keeps_public_access_pending():
    contract = yaml.safe_load(CONTRACT.read_text())
    operation = contract["paths"][
        "/api/v1/events/{event_id}/workshops/launch"
    ]["post"]
    result = contract["components"]["schemas"]["EventWorkshopLaunchResult"]

    assert contract["info"]["version"] == "1.0.0"
    assert operation["responses"]["202"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/EventWorkshopLaunchResult"}
    assert result["properties"]["public_access_state"]["enum"] == [
        "not_required",
        "pending_activation",
    ]


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
