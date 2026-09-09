"""Workshop ordering contract: seats, lifecycle, and idempotent creation."""
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from app.api.deps import provisioning_service as api_provisioning_service
from app.auth.oauth import User, get_current_user
from app.domain.clusters import ClusterTarget
from app.domain.enums import (
    CatalogCategory,
    LabRequestStatus,
    SessionStatus,
    ValidationResultStatus,
    WorkshopSeatStatus,
    WorkshopStatus,
)
from app.domain.lifecycle import transition
from app.domain.models import LabRequest, LabSession, ValidationResult, Workshop, WorkshopSeat
from app.main import app
from app.services.cluster_registry import ClusterRegistry
from app.services.lifecycle_worker import LifecycleQueueService
from app.services.provisioning import ProvisioningService
from app.storage.lifecycle_jobs import InMemoryLifecycleJobStore
from fastapi.testclient import TestClient
from pydantic import ValidationError


def _catalog_with_workshop_limit(
    limit: int, *, allowed_exposure_policies: list[str] | None = None
):
    catalog = SimpleNamespace()
    catalog.get_item = lambda _item_id: SimpleNamespace(
        metadata={
            "max_workshop_seats": limit,
            "promotion_sequence": [1, 5, 25],
            **(
                {"allowed_exposure_policies": allowed_exposure_policies}
                if allowed_exposure_policies is not None
                else {}
            ),
        },
        required_capabilities=[],
    )
    return catalog


client = TestClient(app)


def test_direct_provision_persists_cluster_override_before_creating_seats():
    registry = ClusterRegistry([
        ClusterTarget(
            cluster_id="oberon",
            display_name="Oberon",
            ingress_domain="apps.oberon.example.com",
            capabilities=["cpu", "openshift"],
            local=True,
        ),
        ClusterTarget(
            cluster_id="arena",
            display_name="Arena",
            ingress_domain="apps.arena.example.com",
            capabilities=["cpu", "openshift"],
            credential_secret="launchpad/arena",
        ),
    ])
    service = ProvisioningService(cluster_registry=registry)
    observed_clusters = []

    def provision_seat(workshop, index):
        observed_clusters.append(workshop.cluster_ref)
        seat = workshop.seats[index].model_copy(
            update={"status": WorkshopSeatStatus.READY}
        )
        return seat, f"session-{index}"

    workshop = Workshop(
        tenant_id="placement-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=2,
        target_cluster="oberon",
    )
    with (
        patch.object(service, "check_workshop_capacity", return_value=(True, "ok")),
        patch.object(service, "_provision_workshop_seat", side_effect=provision_seat),
    ):
        result = service.provision_workshop(workshop)

    assert result.cluster_ref == "oberon"
    assert observed_clusters == ["oberon", "oberon"]


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


def test_workshop_order_defaults_name_to_catalog_display_name():
    catalog = _catalog_with_workshop_limit(25)
    item = catalog.get_item("guided-rag-on-xeon")
    item.display_name = "Guided RAG on Intel Xeon"
    catalog.get_item = lambda _item_id: item
    service = ProvisioningService(catalog=catalog)

    order = service.create_workshop_order(
        Workshop(
            tenant_id="tenant",
            catalog_item_id="guided-rag-on-xeon",
            num_users=2,
        )
    )

    assert order.name == "Guided RAG on Intel Xeon"


def test_workshop_order_preserves_explicit_api_name():
    catalog = _catalog_with_workshop_limit(25)
    item = catalog.get_item("guided-rag-on-xeon")
    item.display_name = "Guided RAG on Intel Xeon"
    catalog.get_item = lambda _item_id: item
    service = ProvisioningService(catalog=catalog)

    order = service.create_workshop_order(
        Workshop(
            tenant_id="tenant",
            catalog_item_id="guided-rag-on-xeon",
            num_users=2,
            name="Explicit API workshop name",
        )
    )

    assert order.name == "Explicit API workshop name"


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

    def get(self, workshop_id):
        return self.items.get(workshop_id)


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
    assert response.json()["resource_breakdown"]["per_seat"] == {
        "cpu_millicores": 1000,
        "memory_mib": 2048,
        "pods": 1,
    }
    assert response.json()["resource_breakdown"]["transient"] == {
        "concurrent_seats": 5,
        "cpu_millicores": 0,
        "memory_mib": 0,
        "pods": 0,
    }
    assert response.json()["resource_breakdown"]["shared"] == {
        "cpu_millicores": 0,
        "memory_mib": 0,
        "pods": 0,
    }
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


def test_ha_confirm_enqueues_durable_work_without_api_background_execution(
    monkeypatch,
):
    order = client.post(
        "/api/v1/workshops/orders",
        json={
            "tenant_id": "ha-confirm-tenant",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 1,
        },
    ).json()
    enqueue = Mock(return_value=SimpleNamespace(job_id="job-provision-1"))
    monkeypatch.setenv("LIFECYCLE_HA_ENABLED", "true")
    monkeypatch.setattr(
        "app.api.routers.workshops.lifecycle_queue_service.enqueue_workshop_provision",
        enqueue,
    )

    confirmed = client.post(f"/api/v1/workshops/{order['workshop_id']}/confirm")

    assert confirmed.status_code == 202
    assert confirmed.json()["status"] == "queued"
    enqueue.assert_called_once()
    current = client.get(f"/api/v1/workshops/{order['workshop_id']}").json()
    assert current["status"] == "queued"
    assert current["metadata"]["lifecycle_job_id"] == "job-provision-1"


def test_ha_retry_replaces_a_terminal_provision_job(monkeypatch):
    workshop = Workshop(
        tenant_id="ha-retry-terminal-job-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
        cluster_ref="arena",
        status=WorkshopStatus.PREFLIGHT_FAILED,
    )
    workshop = workshop.model_copy(
        update={
            "seats": [
                WorkshopSeat(workshop_id=workshop.workshop_id, seat_number=1)
            ],
            "metadata": {"preflight_failure": "model endpoint unreachable"},
        }
    )
    api_provisioning_service._save_workshop(workshop)

    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)
    first = queue.enqueue_workshop_provision(workshop)
    claimed = store.claim_next("worker-1", lease_seconds=30)
    assert claimed is not None
    assert store.complete(claimed.job_id, "worker-1", claimed.fencing_token)

    monkeypatch.setenv("LIFECYCLE_HA_ENABLED", "true")
    monkeypatch.setattr(
        "app.api.routers.workshops.lifecycle_queue_service",
        queue,
    )

    response = client.post(f"/api/v1/workshops/{workshop.workshop_id}/retry-failed")

    assert response.status_code == 202
    retried = response.json()
    second = store.get(retried["metadata"]["lifecycle_job_id"])
    assert second is not None
    assert second.job_id != first.job_id
    assert second.status.value == "queued"
    assert second.idempotency_key.endswith(":provision:v2")


def test_ha_direct_workshop_endpoint_also_uses_durable_worker(monkeypatch):
    enqueue = Mock(return_value=SimpleNamespace(job_id="job-direct-provision-1"))
    monkeypatch.setenv("LIFECYCLE_HA_ENABLED", "true")
    monkeypatch.setattr(
        "app.api.routers.workshops.lifecycle_queue_service.enqueue_workshop_provision",
        enqueue,
    )

    with patch.object(api_provisioning_service, "provision_workshop") as direct:
        response = client.post(
            "/api/v1/workshops",
            json={
                "tenant_id": "ha-direct-tenant",
                "catalog_item_id": "inference-overdrive-quickstart",
                "num_users": 1,
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["metadata"]["lifecycle_job_id"] == (
        "job-direct-provision-1"
    )
    enqueue.assert_called_once()
    direct.assert_not_called()


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
        "metadata": {
            **order.metadata,
            "error": "Insufficient capacity during a prior attempt",
            "preflight_failure": "prior endpoint failure",
            "readiness_failures": {"2": "route timed out"},
        },
    }))

    queued = service.queue_failed_workshop_seats(order.workshop_id)

    assert queued.status == WorkshopStatus.QUEUED
    assert queued.seats[0].status == WorkshopSeatStatus.READY
    assert queued.seats[1].status == WorkshopSeatStatus.PENDING
    assert queued.seats[1].error is None
    assert "error" not in queued.metadata
    assert "preflight_failure" not in queued.metadata
    assert "readiness_failures" not in queued.metadata


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


def test_interrupted_workshop_is_automatically_recovered():
    service = ProvisioningService()
    order = service.create_workshop_order(
        Workshop(
            tenant_id="automatic-recovery-tenant",
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

    recovered = service.recover_interrupted_workshops()
    completed = service.get_workshop(order.workshop_id)

    assert recovered == [order.workshop_id]
    assert completed.status == WorkshopStatus.READY
    assert len(completed.session_ids) == 3
    assert all(seat.status == WorkshopSeatStatus.READY for seat in completed.seats)


def test_interrupted_seat_reclaims_persisted_partial_session_before_retry(monkeypatch):
    cleanup = Mock()
    service = ProvisioningService(cleanup=cleanup)
    monkeypatch.setenv("WORKSHOP_RETRY_NAMESPACE_DELETE_TIMEOUT", "7")
    order = service.create_workshop_order(
        Workshop(
            tenant_id="interrupted-seat-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=1,
        )
    )
    seat = order.seats[0]
    request = LabRequest(
        tenant_id=order.tenant_id,
        requester_id=seat.participant_id,
        catalog_item_id=order.catalog_item_id,
        requested_mode=CatalogCategory.QUICK_START,
        metadata={"workshop_id": order.workshop_id, "seat_id": seat.seat_id},
    )
    accepted = service.submit_request(request)
    partial = LabSession(
        request_id=accepted.request_id,
        tenant_id=order.tenant_id,
        catalog_item_id=order.catalog_item_id,
        namespace=f"launchpad-partial-{seat.seat_id[:6]}",
        cluster_ref="arena",
    )
    partial = transition(partial, SessionStatus.PROVISIONING)
    service._save_session(partial)
    service._save_workshop(
        order.model_copy(
            update={
                "status": WorkshopStatus.PROVISIONING,
                "seats": [
                    seat.model_copy(update={"status": WorkshopSeatStatus.PROVISIONING})
                ],
            }
        )
    )

    recovered = service.recover_interrupted_workshops()
    completed = service.get_workshop(order.workshop_id)

    assert recovered == [order.workshop_id]
    cleanup.wait_until_absent.assert_called_once_with(partial.namespace, timeout=7)
    assert service.get_session(partial.session_id).status == SessionStatus.RECLAIMED
    assert completed.status == WorkshopStatus.READY
    assert completed.seats[0].session_id != partial.session_id


def test_takeover_run_cleans_persisted_partial_session_before_retry(monkeypatch):
    """A second HA worker must run the same recovery as process startup."""
    cleanup = Mock()
    service = ProvisioningService(cleanup=cleanup)
    monkeypatch.setenv("WORKSHOP_RETRY_NAMESPACE_DELETE_TIMEOUT", "11")
    order = service.create_workshop_order(
        Workshop(
            tenant_id="takeover-seat-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=1,
        )
    )
    seat = order.seats[0]
    request = LabRequest(
        tenant_id=order.tenant_id,
        requester_id=seat.participant_id,
        catalog_item_id=order.catalog_item_id,
        requested_mode=CatalogCategory.QUICK_START,
        metadata={"workshop_id": order.workshop_id, "seat_id": seat.seat_id},
    )
    accepted = service.submit_request(request)
    partial = LabSession(
        request_id=accepted.request_id,
        tenant_id=order.tenant_id,
        catalog_item_id=order.catalog_item_id,
        namespace=f"launchpad-partial-{seat.seat_id[:6]}",
        cluster_ref="arena",
    )
    partial = transition(partial, SessionStatus.PROVISIONING)
    service._save_session(partial)
    service._save_workshop(
        order.model_copy(
            update={
                "status": WorkshopStatus.PROVISIONING,
                "seats": [
                    seat.model_copy(update={"status": WorkshopSeatStatus.PROVISIONING})
                ],
            }
        )
    )

    completed = service.run_queued_workshop(order.workshop_id)

    cleanup.wait_until_absent.assert_called_once_with(partial.namespace, timeout=11)
    assert service.get_session(partial.session_id).status == SessionStatus.RECLAIMED
    assert completed.status == WorkshopStatus.READY
    assert completed.seats[0].session_id != partial.session_id


def test_interrupted_reclaim_recovers_session_created_before_seat_link():
    service = ProvisioningService()
    order = service.create_workshop_order(
        Workshop(
            tenant_id="reclaim-recovery-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=1,
        )
    )
    seat = order.seats[0]
    request = LabRequest(
        tenant_id=order.tenant_id,
        requester_id=seat.participant_id,
        catalog_item_id=order.catalog_item_id,
        requested_mode=CatalogCategory.QUICK_START,
        metadata={"workshop_id": order.workshop_id, "seat_id": seat.seat_id},
    )
    session = LabSession(
        request_id=request.request_id,
        tenant_id=order.tenant_id,
        catalog_item_id=order.catalog_item_id,
        namespace="launchpad-interrupted-reclaim",
        cluster_ref="arena",
    )
    service._save_request(request)
    service._save_session(session)
    service._save_workshop(
        order.model_copy(
            update={
                "status": WorkshopStatus.RECLAIMING,
                "seats": [
                    seat.model_copy(update={"status": WorkshopSeatStatus.PROVISIONING})
                ],
            }
        )
    )

    def reclaim(workshop_id):
        current = service.get_workshop(workshop_id)
        assert current.session_ids == [session.session_id]
        assert current.seats[0].session_id == session.session_id
        assert current.seats[0].request_id == request.request_id
        completed = current.model_copy(update={"status": WorkshopStatus.COMPLETED})
        service._save_workshop(completed)
        return completed

    with patch.object(service, "reclaim_workshop", side_effect=reclaim) as cleanup:
        recovered = service.recover_interrupted_workshops()

    assert recovered == [order.workshop_id]
    cleanup.assert_called_once_with(order.workshop_id)


def test_reclaim_relink_does_not_replace_a_ready_seat_with_stale_session():
    service = ProvisioningService()
    order = service.create_workshop_order(
        Workshop(
            tenant_id="relink-current-session-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=1,
        )
    )
    seat = order.seats[0]

    def save_session(status: SessionStatus) -> LabSession:
        request = LabRequest(
            tenant_id=order.tenant_id,
            requester_id=seat.participant_id,
            catalog_item_id=order.catalog_item_id,
            requested_mode=CatalogCategory.QUICK_START,
            metadata={"workshop_id": order.workshop_id, "seat_id": seat.seat_id},
        )
        service._save_request(request)
        session = LabSession(
            request_id=request.request_id,
            tenant_id=order.tenant_id,
            catalog_item_id=order.catalog_item_id,
            namespace="launchpad-reused-seat-namespace",
            cluster_ref="arena",
            status=status,
        )
        service._save_session(session)
        return session

    current = save_session(SessionStatus.READY)
    stale = save_session(SessionStatus.RECLAIMED)
    linked_order = order.model_copy(
        update={
            "status": WorkshopStatus.READY,
            "session_ids": [current.session_id],
            "seats": [
                seat.model_copy(
                    update={
                        "status": WorkshopSeatStatus.READY,
                        "session_id": current.session_id,
                        "request_id": current.request_id,
                    }
                )
            ],
        }
    )

    relinked = service._link_persisted_workshop_sessions(linked_order)

    assert stale.session_id not in relinked.session_ids
    assert relinked.session_ids == [current.session_id]
    assert relinked.seats[0].session_id == current.session_id
    assert relinked.seats[0].request_id == current.request_id


def test_queue_reclaim_recovers_session_created_before_failed_seat_link():
    service = ProvisioningService()
    order = service.create_workshop_order(
        Workshop(
            tenant_id="failed-reclaim-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=1,
        )
    )
    seat = order.seats[0]
    request = LabRequest(
        tenant_id=order.tenant_id,
        requester_id=seat.participant_id,
        catalog_item_id=order.catalog_item_id,
        requested_mode=CatalogCategory.QUICK_START,
        metadata={"workshop_id": order.workshop_id, "seat_id": seat.seat_id},
    )
    session = LabSession(
        request_id=request.request_id,
        tenant_id=order.tenant_id,
        catalog_item_id=order.catalog_item_id,
        namespace="launchpad-failed-before-seat-link",
        cluster_ref="arena",
    )
    service._save_request(request)
    service._save_session(session)
    service._save_workshop(
        order.model_copy(
            update={
                "status": WorkshopStatus.FAILED,
                "seats": [
                    seat.model_copy(
                        update={
                            "status": WorkshopSeatStatus.FAILED,
                            "error": "provisioning failed after namespace creation",
                        }
                    )
                ],
            }
        )
    )

    queued = service.queue_workshop_reclaim(order.workshop_id)

    assert queued.session_ids == [session.session_id]
    assert queued.seats[0].session_id == session.session_id
    assert queued.seats[0].request_id == request.request_id
    assert queued.seats[0].status == WorkshopSeatStatus.RECLAIMING


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


def test_idempotent_reclaim_normalizes_unstarted_seat_in_completed_workshop():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="terminal-seat-repair",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
        status=WorkshopStatus.COMPLETED,
        seats=[
            WorkshopSeat(
                workshop_id="terminal-seat-repair",
                seat_number=1,
                status=WorkshopSeatStatus.PENDING,
            )
        ],
    )
    service._save_workshop(workshop)

    repaired = service.queue_workshop_reclaim(workshop.workshop_id)

    assert repaired.status == WorkshopStatus.COMPLETED
    assert repaired.seats[0].status == WorkshopSeatStatus.RECLAIMED
    assert (
        service.get_workshop(workshop.workshop_id).seats[0].status
        == WorkshopSeatStatus.RECLAIMED
    )


def test_capacity_preview_rejects_catalog_certification_seat_limit():
    service = ProvisioningService(catalog=_catalog_with_workshop_limit(1))
    preview = service.preview_workshop_capacity(
        Workshop(
            tenant_id="pilot-tenant",
            catalog_item_id="pilot-lab",
            num_users=2,
        )
    )

    assert preview["can_provision"] is False
    assert preview["catalog_seat_limit"] == 1
    assert preview["reason"] == (
        "pilot-lab is certified for a maximum of 1 workshop seat(s)"
    )


def test_workshop_order_rejects_catalog_certification_seat_limit():
    service = ProvisioningService(catalog=_catalog_with_workshop_limit(1))
    with pytest.raises(ValueError, match="certified for a maximum of 1"):
        service.create_workshop_order(
            Workshop(
                tenant_id="pilot-tenant",
                catalog_item_id="pilot-lab",
                num_users=2,
            )
        )


def test_direct_workshop_provision_rejects_catalog_certification_seat_limit():
    service = ProvisioningService(catalog=_catalog_with_workshop_limit(1))
    with pytest.raises(ValueError, match="certified for a maximum of 1"):
        service.provision_workshop(
            Workshop(
                tenant_id="pilot-tenant",
                catalog_item_id="pilot-lab",
                num_users=2,
            )
        )


def test_admin_certification_override_allows_only_next_declared_promotion_step():
    service = ProvisioningService(catalog=_catalog_with_workshop_limit(1))
    preview = service.preview_workshop_capacity(
        Workshop(
            tenant_id="pilot-tenant",
            catalog_item_id="pilot-lab",
            num_users=5,
            certification_override=True,
        )
    )

    assert preview["can_provision"] is True
    assert preview["catalog_seat_limit"] == 1
    assert preview["certification_override"] is True
    assert preview["certification_target_seats"] == 5


def test_certification_override_rejects_skipping_the_next_promotion_step():
    service = ProvisioningService(catalog=_catalog_with_workshop_limit(1))

    with pytest.raises(ValueError, match="next promotion target of 5"):
        service.create_workshop_order(
            Workshop(
                tenant_id="pilot-tenant",
                catalog_item_id="pilot-lab",
                num_users=25,
                certification_override=True,
            )
        )


def test_certification_override_is_internal_only():
    service = ProvisioningService(catalog=_catalog_with_workshop_limit(1))

    with pytest.raises(ValueError, match="internal workshops only"):
        service.create_workshop_order(
            Workshop(
                tenant_id="pilot-tenant",
                catalog_item_id="pilot-lab",
                num_users=5,
                certification_override=True,
                exposure_policy="public_code",
            )
        )


def test_catalog_can_limit_promoted_workshop_to_internal_exposure():
    service = ProvisioningService(
        catalog=_catalog_with_workshop_limit(
            25, allowed_exposure_policies=["internal"]
        )
    )

    with pytest.raises(ValueError, match="does not allow public_code exposure"):
        service.create_workshop_order(
            Workshop(
                tenant_id="event-tenant",
                catalog_item_id="multi-agent-quickstart",
                num_users=25,
                exposure_policy="public_code",
            )
        )


def test_catalog_can_limit_promoted_individual_lab_to_internal_exposure():
    service = ProvisioningService(
        catalog=_catalog_with_workshop_limit(
            25, allowed_exposure_policies=["internal"]
        )
    )

    result = service.submit_request(
        LabRequest(
            tenant_id="event-tenant",
            requester_id="participant-1",
            catalog_item_id="multi-agent-quickstart",
            requested_mode=CatalogCategory.GUIDED_BUILD,
            exposure_policy="public_code",
        )
    )

    assert result.status == LabRequestStatus.REJECTED


def test_public_workshop_seat_preserves_public_exposure_for_rbac_provisioning():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="event-tenant",
        catalog_item_id="pilot-lab",
        num_users=1,
        exposure_policy="public_code",
    )
    workshop = workshop.model_copy(
        update={
            "seats": [
                WorkshopSeat(
                    workshop_id=workshop.workshop_id,
                    seat_number=1,
                    participant_id="untrusted-request-label",
                )
            ]
        }
    )
    captured = []

    def reject_after_capture(request):
        captured.append(request)
        return request.model_copy(update={"status": LabRequestStatus.REJECTED})

    service.submit_request = reject_after_capture

    service._provision_workshop_seat(workshop, 0)

    assert captured[0].exposure_policy.value == "public_code"


def test_non_admin_cannot_request_workshop_certification_override():
    app.dependency_overrides[get_current_user] = lambda: User(
        username="participant",
        tenant_ids=["pilot-tenant"],
        is_admin=False,
    )
    try:
        response = client.post(
            "/api/v1/workshops/orders",
            json={
                "tenant_id": "pilot-tenant",
                "catalog_item_id": "guided-rag-on-xeon",
                "num_users": 5,
                "certification_override": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Only administrators can request an uncertified workshop size"
    )


def test_admin_api_persists_certification_override_on_draft_order():
    with patch.object(
        api_provisioning_service,
        "catalog",
        _catalog_with_workshop_limit(1),
    ):
        response = client.post(
            "/api/v1/workshops/orders",
            json={
                "tenant_id": "certification-tenant",
                "catalog_item_id": "agentops-observability",
                "num_users": 5,
                "certification_override": True,
                "exposure_policy": "internal",
            },
            headers={"Idempotency-Key": "agentops-five-seat-contract"},
        )

    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "awaiting_confirmation"
    assert order["certification_override"] is True
    assert order["metadata"]["capacity_preview"]["catalog_seat_limit"] == 1
    assert order["metadata"]["capacity_preview"]["certification_target_seats"] == 5


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


def test_workshop_discards_late_seat_when_lifecycle_fence_is_lost():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="fenced-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
    )
    owns_lease = True
    original = service._provision_workshop_seat

    def lose_fence(target_workshop, index):
        nonlocal owns_lease
        result = original(target_workshop, index)
        owns_lease = False
        return result

    with patch.object(
        service,
        "_provision_workshop_seat",
        side_effect=lose_fence,
    ), patch.object(
        service,
        "_discard_late_workshop_session",
        wraps=service._discard_late_workshop_session,
    ) as discard:
        with pytest.raises(RuntimeError, match="lifecycle ownership lost"):
            service.provision_workshop(
                workshop,
                lifecycle_guard=lambda: owns_lease,
            )

    discard.assert_called_once()
    persisted = service.get_workshop(workshop.workshop_id)
    assert persisted is not None
    assert persisted.status == WorkshopStatus.PROVISIONING


def test_lost_workshop_worker_never_persists_late_cleanup_failure():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="fenced-cleanup-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
    )
    owns_lease = True
    save_count_at_loss = 0
    original = service._provision_workshop_seat

    def lose_fence(target_workshop, index):
        nonlocal owns_lease, save_count_at_loss
        result = original(target_workshop, index)
        save_count_at_loss = service._save_workshop.call_count
        owns_lease = False
        return result

    with patch.object(
        service,
        "_provision_workshop_seat",
        side_effect=lose_fence,
    ), patch.object(
        service,
        "_reclaim_workshop_session",
        return_value="simulated cleanup failure",
    ), patch.object(
        service,
        "_save_workshop",
        wraps=service._save_workshop,
    ) as save:
        with pytest.raises(RuntimeError, match="lifecycle ownership lost"):
            service.provision_workshop(
                workshop,
                lifecycle_guard=lambda: owns_lease,
            )

    # The stale worker may persist its initial provisioning state, but it must
    # never write again after losing the lifecycle fence.
    assert save.call_count == save_count_at_loss
    persisted = service.get_workshop(workshop.workshop_id)
    assert persisted is not None
    assert persisted.status == WorkshopStatus.PROVISIONING


def test_workshop_provisioning_uses_catalog_specific_concurrency():
    service = ProvisioningService()
    item = service.catalog.get_item("inference-overdrive-quickstart")
    item.metadata = {**item.metadata, "workshop_provision_concurrency": 2}
    workshop = Workshop(
        tenant_id="catalog-concurrency-tenant",
        catalog_item_id=item.catalog_item_id,
        num_users=4,
    )
    original = service._provision_workshop_seat
    lock = threading.Lock()
    active = 0
    peak = 0

    def tracked(target_workshop, index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.03)
            return original(target_workshop, index)
        finally:
            with lock:
                active -= 1

    with patch.object(service, "_provision_workshop_seat", side_effect=tracked):
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


def test_collective_readiness_failure_prevents_workshop_ready():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="collective-readiness-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=2,
    )

    with patch.object(
        service,
        "_wait_for_workshop_stability",
        return_value={2: "showroom endpoint was not stable"},
    ):
        result = service.provision_workshop(workshop)

    assert result.status == WorkshopStatus.PARTIALLY_READY
    assert result.seats[0].status == WorkshopSeatStatus.READY
    assert result.seats[1].status == WorkshopSeatStatus.FAILED
    assert len(result.session_ids) == 1
    assert result.metadata["readiness_failures"] == {
        "2": "showroom endpoint was not stable"
    }


def test_collective_readiness_verifies_routes_with_the_configured_ca_bundle(monkeypatch):
    service = ProvisioningService()
    seat = WorkshopSeat(
        workshop_id="workshop-ca",
        seat_number=1,
        status=WorkshopSeatStatus.READY,
        lab_url="https://showroom.example.com",
    )
    monkeypatch.setenv("LAUNCHPAD_MODE", "openshift")
    monkeypatch.setenv("WORKSHOP_STABILITY_PASSES", "1")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/etc/launchpad-ca/ca-bundle.crt")

    with patch("requests.get", return_value=SimpleNamespace(status_code=200)) as get:
        failures = service._wait_for_workshop_stability([seat])

    assert failures == {}
    get.assert_called_once_with(
        "https://showroom.example.com",
        timeout=10,
        verify="/etc/launchpad-ca/ca-bundle.crt",
    )


def test_collective_readiness_retry_reuses_existing_session():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="collective-retry-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
    )
    with patch.object(
        service,
        "_wait_for_workshop_stability",
        return_value={1: "showroom endpoint was not stable"},
    ):
        first = service.provision_workshop(workshop)
    original_session_id = first.seats[0].session_id
    queued = service.queue_failed_workshop_seats(first.workshop_id)

    with patch.object(service, "_wait_for_workshop_stability", return_value={}):
        retried = service.provision_workshop(queued)

    assert retried.status == WorkshopStatus.READY
    assert retried.seats[0].session_id == original_session_id
    assert len(service._sessions) == 1


def test_failed_seat_retry_revalidates_existing_validation_failed_session():
    validator = Mock()
    validator.validate.side_effect = [
        [
            ValidationResult(
                session_id="session",
                check_name="operator-rollout",
                result=ValidationResultStatus.FAIL,
                message="terminating rollout pod observed",
            )
        ],
        [
            ValidationResult(
                session_id="session",
                check_name="operator-rollout",
                result=ValidationResultStatus.PASS,
                message="healthy replacement is ready",
            )
        ],
    ]
    service = ProvisioningService(validator=validator)
    workshop = Workshop(
        tenant_id="validation-retry-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
    )

    first = service.provision_workshop(workshop)
    original_session_id = first.seats[0].session_id
    assert service.get_session(original_session_id).status == SessionStatus.VALIDATION_FAILED

    queued = service.queue_failed_workshop_seats(first.workshop_id)
    retried = service.provision_workshop(queued)

    assert retried.status == WorkshopStatus.READY
    assert retried.seats[0].session_id == original_session_id
    assert service.get_session(original_session_id).status == SessionStatus.READY
    assert validator.validate.call_count == 2
    assert len(service._sessions) == 1


def test_retry_capacity_counts_only_seats_without_existing_sessions():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="retry-capacity-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=2,
    )
    with patch.object(
        service,
        "_wait_for_workshop_stability",
        return_value={2: "showroom endpoint was not stable"},
    ):
        first = service.provision_workshop(workshop)
    queued = service.queue_failed_workshop_seats(first.workshop_id)

    with patch.object(service, "check_workshop_capacity") as capacity:
        with patch.object(service, "_wait_for_workshop_stability", return_value={}):
            retried = service.provision_workshop(queued)

    assert retried.status == WorkshopStatus.READY
    capacity.assert_not_called()


def test_reclaim_waits_for_inflight_provisioning_without_status_overwrite():
    service = ProvisioningService()
    workshop = Workshop(
        tenant_id="cancel-inflight-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=2,
    )
    seat_started = threading.Event()
    allow_seats_to_finish = threading.Event()
    original = service._provision_workshop_seat

    def blocked_seat(target_workshop, index):
        seat_started.set()
        assert allow_seats_to_finish.wait(timeout=2)
        return original(target_workshop, index)

    provision_result = {}
    reclaim_result = {}

    def provision():
        provision_result["workshop"] = service.provision_workshop(workshop)

    def reclaim():
        reclaim_result["workshop"] = service.reclaim_workshop(workshop.workshop_id)

    with (
        patch.object(service, "_provision_workshop_seat", side_effect=blocked_seat),
        patch.dict(os.environ, {"WORKSHOP_PROVISION_CONCURRENCY": "2"}),
    ):
        provision_thread = threading.Thread(target=provision)
        provision_thread.start()
        assert seat_started.wait(timeout=2)

        queued = service.queue_workshop_reclaim(workshop.workshop_id)
        assert queued.status == WorkshopStatus.RECLAIMING
        reclaim_thread = threading.Thread(target=reclaim)
        reclaim_thread.start()
        assert reclaim_thread.is_alive()

        allow_seats_to_finish.set()
        provision_thread.join(timeout=5)
        reclaim_thread.join(timeout=5)

    assert not provision_thread.is_alive()
    assert not reclaim_thread.is_alive()
    assert provision_result["workshop"].status == WorkshopStatus.RECLAIMING
    assert reclaim_result["workshop"].status == WorkshopStatus.COMPLETED
    assert all(
        seat.status == WorkshopSeatStatus.RECLAIMED
        for seat in reclaim_result["workshop"].seats
    )


def test_stale_worker_reclaims_late_seat_after_another_process_completes_order():
    """A rolling replacement must not let the old worker recreate an order.

    The persisted workshop is authoritative across backend processes.  This
    models one process completing reclaim while a stale process finishes a
    seat that already mutated the execution cluster.
    """
    store = InMemoryWorkshopStore()
    service = ProvisioningService(db_stores=SimpleNamespace(workshops=store))
    workshop = Workshop(
        tenant_id="stale-worker-tenant",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
    )
    seat_started = threading.Event()
    allow_seat_to_finish = threading.Event()
    late_session = LabSession(
        request_id="late-request",
        tenant_id=workshop.tenant_id,
        catalog_item_id=workshop.catalog_item_id,
        namespace="launchpad-late-seat",
        status=SessionStatus.READY,
    )

    def late_seat(target_workshop, index):
        seat_started.set()
        assert allow_seat_to_finish.wait(timeout=2)
        service._save_session(late_session)
        return target_workshop.seats[index].model_copy(
            update={
                "status": WorkshopSeatStatus.READY,
                "session_id": late_session.session_id,
                "request_id": late_session.request_id,
            }
        ), late_session.session_id

    result = {}

    def provision():
        result["workshop"] = service.provision_workshop(workshop)

    with (
        patch.object(service, "_provision_workshop_seat", side_effect=late_seat),
        patch.object(
            service, "_reclaim_workshop_session", return_value=None
        ) as reclaim,
    ):
        thread = threading.Thread(target=provision)
        thread.start()
        assert seat_started.wait(timeout=2)

        persisted = store.get(workshop.workshop_id)
        store.save(
            persisted.model_copy(
                update={
                    "status": WorkshopStatus.COMPLETED,
                    "completed_at": persisted.started_at,
                    "seats": [
                        persisted.seats[0].model_copy(
                            update={"status": WorkshopSeatStatus.RECLAIMED}
                        )
                    ],
                }
            )
        )
        allow_seat_to_finish.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    reclaim.assert_called_once_with(late_session.session_id)
    assert result["workshop"].status == WorkshopStatus.COMPLETED
    assert store.get(workshop.workshop_id).status == WorkshopStatus.COMPLETED


def test_reclaim_cancels_workshop_seats_that_have_not_started():
    service = ProvisioningService()
    item = service.catalog.get_item("inference-overdrive-quickstart")
    item.metadata = {**item.metadata, "workshop_provision_concurrency": 1}
    workshop = Workshop(
        tenant_id="cancel-pending-tenant",
        catalog_item_id=item.catalog_item_id,
        num_users=3,
    )
    first_seat_started = threading.Event()
    allow_first_seat_to_finish = threading.Event()
    original = service._provision_workshop_seat
    started_indexes = []

    def tracked(target_workshop, index):
        started_indexes.append(index)
        if index == 0:
            first_seat_started.set()
            assert allow_first_seat_to_finish.wait(timeout=2)
        return original(target_workshop, index)

    result = {}

    def provision():
        result["workshop"] = service.provision_workshop(workshop)

    with patch.object(service, "_provision_workshop_seat", side_effect=tracked):
        thread = threading.Thread(target=provision)
        thread.start()
        assert first_seat_started.wait(timeout=2)
        service.queue_workshop_reclaim(workshop.workshop_id)
        allow_first_seat_to_finish.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert started_indexes == [0]
    assert result["workshop"].status == WorkshopStatus.RECLAIMING
    # The in-flight seat is reclaimed immediately once its result observes
    # the group stop state; the final reclaim relinks the persisted record so
    # its seat-level audit trail is still complete.
    assert result["workshop"].session_ids == []
    assert {
        session.status for session in service._sessions.values()
    } == {SessionStatus.RECLAIMED}

    reclaimed = service.reclaim_workshop(workshop.workshop_id)
    assert reclaimed.status == WorkshopStatus.COMPLETED
    assert all(
        seat.status == WorkshopSeatStatus.RECLAIMED for seat in reclaimed.seats
    )


def test_reclaim_relinks_failed_sessions_after_inflight_provisioning_stops():
    service = ProvisioningService()
    order = service.create_workshop_order(
        Workshop(
            tenant_id="relink-failed-reclaim-tenant",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2,
        )
    )
    sessions = []
    seats = []
    for index, seat in enumerate(order.seats):
        request = LabRequest(
            tenant_id=order.tenant_id,
            requester_id=seat.participant_id,
            catalog_item_id=order.catalog_item_id,
            requested_mode=CatalogCategory.QUICK_START,
            metadata={"workshop_id": order.workshop_id, "seat_id": seat.seat_id},
        )
        session = LabSession(
            request_id=request.request_id,
            tenant_id=order.tenant_id,
            catalog_item_id=order.catalog_item_id,
            namespace=f"launchpad-relink-seat-{index + 1}",
            cluster_ref="arena",
        )
        service._save_request(request)
        service._save_session(session)
        sessions.append(session)
        seats.append(
            seat.model_copy(
                update={
                    "status": (
                        WorkshopSeatStatus.RECLAIMING
                        if index == 0
                        else WorkshopSeatStatus.FAILED
                    ),
                    "session_id": session.session_id,
                    "request_id": request.request_id,
                }
            )
        )

    # This is the stale state observed when provisioning overwrites the links
    # recovered by queue_workshop_reclaim: only the successful seat remains in
    # session_ids even though both persisted sessions own cluster resources.
    service._save_workshop(
        order.model_copy(
            update={
                "status": WorkshopStatus.RECLAIMING,
                "session_ids": [sessions[0].session_id],
                "seats": seats,
            }
        )
    )

    with patch.object(
        service, "_reclaim_workshop_session", return_value=None
    ) as reclaim:
        completed = service.reclaim_workshop(order.workshop_id)

    assert {call.args[0] for call in reclaim.call_args_list} == {
        session.session_id for session in sessions
    }
    assert completed.status == WorkshopStatus.COMPLETED
    assert completed.session_ids == [session.session_id for session in sessions]
    assert {seat.status for seat in completed.seats} == {
        WorkshopSeatStatus.RECLAIMED
    }
