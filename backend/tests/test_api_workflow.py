"""
API-level workflow tests — full HTTP round-trip for Launch Lab flow.
"""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import provisioning_service, tenant_store
from app.main import app


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
    resp = client.post("/lab-requests", json=REQUEST_PAYLOAD)
    assert resp.status_code == 201
    request_id = resp.json()["request_id"]
    assert resp.json()["status"] == "accepted"

    # Step 2: Provision
    resp = client.post(f"/lab-requests/{request_id}/provision")
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    assert resp.json()["status"] == "validating"
    assert resp.json()["namespace"] is not None
    assert resp.json()["lab_url"] is not None

    # Step 3: Validate
    resp = client.post(f"/lab-sessions/{session_id}/validate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert len(resp.json()["validation_results"]) == 3

    # Step 4: Verify handoff
    resp = client.get(f"/lab-sessions/{session_id}/handoff")
    assert resp.status_code == 200
    assert resp.json()["lab_url"] is not None

    # Step 5: Verify showback
    resp = client.get(f"/lab-sessions/{session_id}/showback")
    assert resp.status_code == 200
    assert resp.json()["duration_seconds"] > 0

    # Step 6: Verify repeatability
    resp = client.get(f"/lab-sessions/{session_id}/repeatability-report")
    assert resp.status_code == 200
    assert resp.json()["repeatability_score"] == 100


def test_api_workflow_rejects_bad_request(client):
    bad_payload = {**REQUEST_PAYLOAD, "catalog_item_id": "nonexistent"}
    resp = client.post("/lab-requests", json=bad_payload)
    assert resp.status_code == 201
    assert resp.json()["status"] == "rejected"

    # Cannot provision a rejected request
    request_id = resp.json()["request_id"]
    resp = client.post(f"/lab-requests/{request_id}/provision")
    assert resp.status_code == 400


def test_api_workflow_provision_missing_request(client):
    resp = client.post("/lab-requests/fake-id/provision")
    assert resp.status_code == 400
