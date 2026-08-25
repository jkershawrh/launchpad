"""Workshop ordering contract: seats, lifecycle, and idempotent creation."""
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

    assert reclaimed.status_code == 200
    assert reclaimed.json()["status"] == "completed"
    assert {seat["status"] for seat in reclaimed.json()["seats"]} == {"reclaimed"}


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
