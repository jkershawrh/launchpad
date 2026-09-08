"""
API-level workflow tests — full HTTP round-trip for Launch Lab flow.
"""
from unittest.mock import patch

import pytest
from app.api.deps import (
    lifecycle_queue_service,
    provisioning_service,
    tenant_store,
)
from app.domain.enums import SessionStatus
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_state():
    tenant_store._tenants.clear()
    provisioning_service._requests.clear()
    provisioning_service._sessions.clear()
    provisioning_service._plans.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


REQUEST_PAYLOAD = {
    "tenant_id": "partner-oem-a",
    "requester_id": "demo-engineer-1",
    "catalog_item_id": "inference-overdrive-quickstart",
    "requested_mode": "quick_start",
    "persistence": "ephemeral",
    "ttl": "4h",
    "hardware_profile": "gaudi-endpoint",
    "quota_profile": "standard",
}


def test_api_workflow_submit_to_ready(client):
    # Step 1: Submit request
    resp = client.post("/api/v1/lab-requests", json=REQUEST_PAYLOAD)
    assert resp.status_code == 201
    request_id = resp.json()["request_id"]
    assert resp.json()["status"] == "accepted"

    # Step 2: Provision
    resp = client.post(f"/api/v1/lab-requests/{request_id}/provision")
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    assert resp.json()["status"] == "validating"
    assert resp.json()["namespace"] is not None
    assert resp.json()["lab_url"] is not None

    # Step 3: Validate
    resp = client.post(f"/api/v1/lab-sessions/{session_id}/validate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert len(resp.json()["validation_results"]) == 3

    # Step 4: Verify handoff
    resp = client.get(f"/api/v1/lab-sessions/{session_id}/handoff")
    assert resp.status_code == 200
    assert resp.json()["lab_url"] is not None

    # Step 5: Verify showback
    resp = client.get(f"/api/v1/lab-sessions/{session_id}/showback")
    assert resp.status_code == 200
    assert resp.json()["duration_seconds"] > 0

    # Step 6: Verify repeatability
    resp = client.get(f"/api/v1/lab-sessions/{session_id}/repeatability-report")
    assert resp.status_code == 200
    assert resp.json()["repeatability_score"] == 100


def test_api_workflow_rejects_bad_request(client):
    bad_payload = {**REQUEST_PAYLOAD, "catalog_item_id": "nonexistent"}
    resp = client.post("/api/v1/lab-requests", json=bad_payload)
    assert resp.status_code == 201
    assert resp.json()["status"] == "rejected"

    # Cannot provision a rejected request
    request_id = resp.json()["request_id"]
    resp = client.post(f"/api/v1/lab-requests/{request_id}/provision")
    assert resp.status_code == 400


def test_api_workflow_provision_missing_request(client):
    resp = client.post("/api/v1/lab-requests/fake-id/provision")
    # Missing and inaccessible requests intentionally share the same response
    # so the API does not disclose another tenant's request identifiers.
    assert resp.status_code == 404


def test_ha_provision_returns_persisted_session_and_durable_job(client):
    payload = {**REQUEST_PAYLOAD, "metadata": {"target_cluster": "arena"}}
    created = client.post("/api/v1/lab-requests", json=payload)
    request_id = created.json()["request_id"]

    with (
        patch.dict("os.environ", {"LIFECYCLE_HA_ENABLED": "true"}, clear=False),
        patch.object(
            lifecycle_queue_service,
            "enqueue_session_provision",
            wraps=lifecycle_queue_service.enqueue_session_provision,
        ) as enqueue,
    ):
        response = client.post(f"/api/v1/lab-requests/{request_id}/provision")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "requested"
    assert body["cluster_ref"] == "arena"
    assert body["metadata"]["lifecycle_job_id"]
    enqueue.assert_called_once()


def test_ha_reclaim_queues_cleanup_without_running_it_in_api(client):
    payload = {**REQUEST_PAYLOAD, "metadata": {"target_cluster": "arena"}}
    created = client.post("/api/v1/lab-requests", json=payload)
    prepared = provisioning_service.prepare_session_provision(
        created.json()["request_id"]
    )
    provisioning_service._save_session(
        prepared.model_copy(update={"status": SessionStatus.READY})
    )

    with (
        patch.dict("os.environ", {"LIFECYCLE_HA_ENABLED": "true"}, clear=False),
        patch.object(
            lifecycle_queue_service,
            "enqueue_session_reclaim",
            wraps=lifecycle_queue_service.enqueue_session_reclaim,
        ) as enqueue,
        patch.object(provisioning_service, "reclaim_session") as reclaim,
    ):
        response = client.post(
            f"/api/v1/lab-sessions/{prepared.session_id}/reclaim"
        )

    assert response.status_code == 202
    assert response.json()["status"] == "resetting"
    assert response.json()["metadata"]["lifecycle_job_id"]
    enqueue.assert_called_once()
    reclaim.assert_not_called()
