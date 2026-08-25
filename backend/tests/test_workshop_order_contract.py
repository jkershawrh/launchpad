"""Workshop ordering contract: seats, lifecycle, and idempotent creation."""
import os
import threading
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.domain.enums import WorkshopSeatStatus, WorkshopStatus
from app.domain.models import Workshop, WorkshopSeat
from app.main import app
from app.services.provisioning import ProvisioningService
from types import SimpleNamespace


client = TestClient(app)


def test_workshop_rejects_non_positive_seat_count():
    with pytest.raises(ValidationError):
        Workshop(tenant_id="tenant", catalog_item_id="guided-rag-on-xeon", num_users=0)


def test_workshop_rejects_more_than_one_hundred_seats():
    with pytest.raises(ValidationError):
        Workshop(tenant_id="tenant", catalog_item_id="guided-rag-on-xeon", num_users=101)


@pytest.mark.parametrize("seat_count", [0, 101])
def test_api_rejects_invalid_seat_count(seat_count):
    response = client.post(
        "/api/v1/workshops",
        json={
            "tenant_id": "tenant",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": seat_count,
        },
    )
    assert response.status_code == 422


def test_seat_contract_tracks_independent_lifecycle():
    seat = WorkshopSeat(workshop_id="workshop-1", seat_number=1, participant_id="user1")
    assert seat.status == WorkshopSeatStatus.PENDING
    assert seat.session_id is None


def test_workshop_uses_typed_lifecycle_status():
    workshop = Workshop(tenant_id="tenant", catalog_item_id="guided-rag-on-xeon", num_users=20)
    assert workshop.status == WorkshopStatus.DRAFT
    assert workshop.seats == []


def test_create_workshop_is_idempotent_for_same_tenant_and_key():
    payload = {
        "tenant_id": "idempotent-tenant",
        "catalog_item_id": "guided-rag-on-xeon",
        "num_users": 2,
        "ttl": "4h",
        "name": "Partner workshop",
        "owner_id": "instructor@example.com",
    }
    headers = {"Idempotency-Key": "partner-workshop-2026-08-25"}

    first = client.post("/api/v1/workshops", json=payload, headers=headers)
    second = client.post("/api/v1/workshops", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["workshop_id"] == second.json()["workshop_id"]
    assert len(first.json()["seats"]) == 2
    assert [seat["seat_number"] for seat in first.json()["seats"]] == [1, 2]


def test_idempotency_key_cannot_be_reused_for_different_order():
    headers = {"Idempotency-Key": "conflicting-workshop-order"}
    base = {
        "tenant_id": "conflict-tenant",
        "catalog_item_id": "guided-rag-on-xeon",
        "num_users": 2,
    }
    assert client.post("/api/v1/workshops", json=base, headers=headers).status_code == 201

    conflict = client.post(
        "/api/v1/workshops",
        json={**base, "num_users": 3},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_group_reclaim_updates_every_seat():
    response = client.post(
        "/api/v1/workshops",
        json={
            "tenant_id": "seat-reclaim-tenant",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 2,
        },
    )
    workshop_id = response.json()["workshop_id"]

    reclaimed = client.delete(f"/api/v1/workshops/{workshop_id}")

    assert reclaimed.status_code == 202
    assert reclaimed.json()["status"] == "reclaiming"
    assert {seat["status"] for seat in reclaimed.json()["seats"]} == {"reclaiming"}

    completed = client.get(f"/api/v1/workshops/{workshop_id}")
    assert completed.json()["status"] == "completed"
    assert {seat["status"] for seat in completed.json()["seats"]} == {"reclaimed"}


class InMemoryWorkshopStore:
    def __init__(self):
        self.items = {}

    def save(self, workshop):
        self.items[workshop.workshop_id] = workshop

    def list_all(self):
        return list(self.items.values())


def test_idempotency_survives_service_restart():
    store = InMemoryWorkshopStore()
    db = SimpleNamespace(workshops=store)
    order = Workshop(
        tenant_id="restart-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=2,
    )

    first_service = ProvisioningService(db_stores=db)
    first = first_service.provision_workshop(order, idempotency_key="restart-safe")

    restarted_service = ProvisioningService(db_stores=db)
    duplicate = restarted_service.provision_workshop(
        Workshop(
            tenant_id="restart-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2,
        ),
        idempotency_key="restart-safe",
    )

    assert duplicate.workshop_id == first.workshop_id
    assert len(store.items) == 1


def test_capacity_preview_does_not_create_workshop():
    before = client.get("/api/v1/workshops").json()
    response = client.post(
        "/api/v1/workshops/capacity-preview",
        json={
            "tenant_id": "preview-tenant",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 20,
            "ttl": "4h",
        },
    )
    after = client.get("/api/v1/workshops").json()

    assert response.status_code == 200
    assert response.json()["seats_requested"] == 20
    assert response.json()["can_provision"] is True
    assert response.json()["estimated_resources"]["cpu_millicores"] == 20000
    assert len(after) == len(before)


def test_order_waits_for_confirmation_before_provisioning():
    response = client.post(
        "/api/v1/workshops/orders",
        json={
            "tenant_id": "confirmation-tenant",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 3,
            "ttl": "4h",
        },
        headers={"Idempotency-Key": "confirmation-order"},
    )

    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "awaiting_confirmation"
    assert len(order["seats"]) == 3
    assert order["session_ids"] == []
    assert order["metadata"]["capacity_preview"]["can_provision"] is True

    confirmed = client.post(f"/api/v1/workshops/{order['workshop_id']}/confirm")
    assert confirmed.status_code == 202
    assert confirmed.json()["status"] == "queued"
    completed = client.get(f"/api/v1/workshops/{order['workshop_id']}")
    assert completed.json()["status"] == "ready"
    assert len(completed.json()["session_ids"]) == 3


def test_confirm_is_idempotent_after_workshop_is_ready():
    order = client.post(
        "/api/v1/workshops/orders",
        json={
            "tenant_id": "confirm-twice-tenant",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 1,
        },
    ).json()
    first = client.post(f"/api/v1/workshops/{order['workshop_id']}/confirm")
    second = client.post(f"/api/v1/workshops/{order['workshop_id']}/confirm")

    assert first.status_code == 202
    assert second.status_code == 202
    completed = client.get(f"/api/v1/workshops/{order['workshop_id']}").json()
    assert second.json()["session_ids"] == completed["session_ids"]


def test_queued_order_can_resume_after_service_restart():
    store = InMemoryWorkshopStore()
    db = SimpleNamespace(workshops=store)
    service = ProvisioningService(db_stores=db)
    order = service.create_workshop_order(
        Workshop(
            tenant_id="queued-restart-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2,
        )
    )
    service.queue_workshop(order.workshop_id)

    restarted = ProvisioningService(db_stores=db)
    completed = restarted.run_queued_workshop(order.workshop_id)

    assert completed.status == WorkshopStatus.READY
    assert len(completed.session_ids) == 2


def test_failed_workshop_seats_can_be_requeued_without_resetting_ready_seats():
    service = ProvisioningService()
    order = service.create_workshop_order(
        Workshop(
            tenant_id="retry-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2,
        )
    )
    seats = [
        order.seats[0].model_copy(update={"status": WorkshopSeatStatus.READY}),
        order.seats[1].model_copy(update={
            "status": WorkshopSeatStatus.FAILED,
            "error": "route timed out",
        }),
    ]
    service._save_workshop(order.model_copy(update={
        "status": WorkshopStatus.PARTIALLY_READY,
        "seats": seats,
    }))

    queued = service.queue_failed_workshop_seats(order.workshop_id)

    assert queued.status == WorkshopStatus.QUEUED
    assert queued.seats[0].status == WorkshopSeatStatus.READY
    assert queued.seats[1].status == WorkshopSeatStatus.PENDING
    assert queued.seats[1].error is None


def test_interrupted_workshop_seats_can_be_requeued_without_resetting_ready_seats():
    service = ProvisioningService()
    order = service.create_workshop_order(
        Workshop(
            tenant_id="retry-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=3,
        )
    )
    seats = [
        order.seats[0].model_copy(update={"status": WorkshopSeatStatus.READY}),
        order.seats[1].model_copy(update={"status": WorkshopSeatStatus.PROVISIONING}),
        order.seats[2].model_copy(update={"status": WorkshopSeatStatus.PENDING}),
    ]
    service._save_workshop(order.model_copy(update={
        "status": WorkshopStatus.PROVISIONING,
        "seats": seats,
    }))

    queued = service.queue_failed_workshop_seats(order.workshop_id)

    assert queued.status == WorkshopStatus.QUEUED
    assert queued.seats[0].status == WorkshopSeatStatus.READY
    assert queued.seats[1].status == WorkshopSeatStatus.PENDING
    assert queued.seats[2].status == WorkshopSeatStatus.PENDING


def test_workshop_order_rejects_more_than_supported_seat_limit():
    service = ProvisioningService()
    with patch.dict(os.environ, {"MAX_ACTIVE_SESSIONS_PER_WORKSHOP": "20"}):
        with pytest.raises(ValueError, match="supported limit of 20"):
            service.create_workshop_order(
                Workshop(
                    tenant_id="limit-tenant",
                    catalog_item_id="inference-overdrive-quickstart",
                    num_users=21,
                )
            )


def test_workshop_provisioning_respects_bounded_concurrency():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="parallel-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=4,
    )
    original = service._provision_workshop_seat
    lock = threading.Lock()
    active = 0
    peak = 0

    def tracked(workshop, index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.03)
            return original(workshop, index)
        finally:
            with lock:
                active -= 1

    with patch.object(service, "_provision_workshop_seat", side_effect=tracked):
        with patch.dict(os.environ, {"WORKSHOP_PROVISION_CONCURRENCY": "2"}):
            provisioned = service.provision_workshop(workshop)

    assert provisioned.status == WorkshopStatus.READY
    assert peak == 2


def test_workshop_reclaim_respects_bounded_concurrency():
    service = ProvisioningService()
    workshop = service.provision_workshop(Workshop(
        tenant_id="parallel-reclaim-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=4,
    ))
    original = service._reclaim_workshop_session
    lock = threading.Lock()
    active = 0
    peak = 0

    def tracked(session_id):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.03)
            return original(session_id)
        finally:
            with lock:
                active -= 1

    with patch.object(service, "_reclaim_workshop_session", side_effect=tracked):
        with patch.dict(os.environ, {"WORKSHOP_RECLAIM_CONCURRENCY": "3"}):
            reclaimed = service.reclaim_workshop(workshop.workshop_id)

    assert reclaimed.status == WorkshopStatus.COMPLETED
    assert peak == 3
