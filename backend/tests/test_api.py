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


TENANT_PAYLOAD = {
    "tenant_id": "partner-oem-a",
    "display_name": "Partner OEM A",
    "tenant_type": "partner",
    "branding_profile_id": "partner-oem-a",
    "default_quota_profile": "standard",
    "default_ttl": "8h",
}

LAB_REQUEST_PAYLOAD = {
    "tenant_id": "partner-oem-a",
    "requester_id": "demo-engineer-1",
    "catalog_item_id": "inference-overdrive-quickstart",
    "requested_mode": "quick_start",
    "persistence": "ephemeral",
    "ttl": "4h",
    "hardware_profile": "gaudi-endpoint",
    "quota_profile": "standard",
    "branding_profile_id": "partner-oem-a",
}


def test_api_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --- Tenant endpoints ---

def test_api_can_create_tenant(client):
    resp = client.post("/tenants", json=TENANT_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["tenant_id"] == "partner-oem-a"
    assert data["tenant_type"] == "partner"


def test_api_can_list_tenants(client):
    client.post("/tenants", json=TENANT_PAYLOAD)
    resp = client.get("/tenants")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_api_can_get_tenant(client):
    client.post("/tenants", json=TENANT_PAYLOAD)
    resp = client.get("/tenants/partner-oem-a")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Partner OEM A"


def test_api_tenant_not_found(client):
    resp = client.get("/tenants/nonexistent")
    assert resp.status_code == 404


def test_api_tenant_duplicate(client):
    client.post("/tenants", json=TENANT_PAYLOAD)
    resp = client.post("/tenants", json=TENANT_PAYLOAD)
    assert resp.status_code == 409


# --- Catalog endpoints ---

def test_api_can_list_catalog(client):
    resp = client.get("/catalog")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 18
    ids = {i["catalog_item_id"] for i in items}
    assert "inference-overdrive-quickstart" in ids


def test_api_can_get_catalog_item(client):
    resp = client.get("/catalog/inference-overdrive-quickstart")
    assert resp.status_code == 200
    assert resp.json()["category"] == "quick_start"


def test_api_catalog_not_found(client):
    resp = client.get("/catalog/nonexistent")
    assert resp.status_code == 404


# --- Lab Request endpoints ---

def test_api_can_create_lab_request(client):
    resp = client.post("/lab-requests", json=LAB_REQUEST_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["request_id"]


def test_api_lab_request_rejected_for_unknown_item(client):
    payload = {**LAB_REQUEST_PAYLOAD, "catalog_item_id": "nonexistent"}
    resp = client.post("/lab-requests", json=payload)
    assert resp.status_code == 201
    assert resp.json()["status"] == "rejected"


def test_api_can_list_lab_requests(client):
    client.post("/lab-requests", json=LAB_REQUEST_PAYLOAD)
    resp = client.get("/lab-requests")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_api_can_get_lab_request(client):
    create_resp = client.post("/lab-requests", json=LAB_REQUEST_PAYLOAD)
    request_id = create_resp.json()["request_id"]
    resp = client.get(f"/lab-requests/{request_id}")
    assert resp.status_code == 200


# --- Provisioning + Session lifecycle ---

def _create_and_provision(client):
    create_resp = client.post("/lab-requests", json=LAB_REQUEST_PAYLOAD)
    request_id = create_resp.json()["request_id"]
    prov_resp = client.post(f"/lab-requests/{request_id}/provision")
    return prov_resp


def test_api_can_provision_mock_lab(client):
    resp = _create_and_provision(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "validating"
    assert data["namespace"] is not None
    assert data["lab_url"] is not None


def test_api_can_list_sessions(client):
    _create_and_provision(client)
    resp = client.get("/lab-sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_api_can_get_session(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    resp = client.get(f"/lab-sessions/{session_id}")
    assert resp.status_code == 200


def test_api_can_validate_lab_session(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    resp = client.post(f"/lab-sessions/{session_id}/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert len(data["validation_results"]) == 3


def test_api_can_activate_session(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    client.post(f"/lab-sessions/{session_id}/validate")
    resp = client.post(f"/lab-sessions/{session_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_api_can_reset_session(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    client.post(f"/lab-sessions/{session_id}/validate")
    client.post(f"/lab-sessions/{session_id}/activate")
    resp = client.post(f"/lab-sessions/{session_id}/reset")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resetting"


def test_api_can_reclaim_session(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    client.post(f"/lab-sessions/{session_id}/validate")
    client.post(f"/lab-sessions/{session_id}/activate")
    client.post(f"/lab-sessions/{session_id}/reset")
    resp = client.post(f"/lab-sessions/{session_id}/reclaim")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reclaimed"


# --- Report endpoints ---

def test_api_can_get_handoff(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    client.post(f"/lab-sessions/{session_id}/validate")
    resp = client.get(f"/lab-sessions/{session_id}/handoff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lab_title"] == "Inference Overdrive Quick Start"
    assert data["lab_url"] is not None


def test_api_can_get_showback(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    resp = client.get(f"/lab-sessions/{session_id}/showback")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "partner-oem-a"
    assert data["duration_seconds"] > 0


def test_api_can_get_repeatability_report(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    client.post(f"/lab-sessions/{session_id}/validate")
    resp = client.get(f"/lab-sessions/{session_id}/repeatability-report")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repeatability_score"] == 100


def test_api_can_get_security_plan(client):
    prov = _create_and_provision(client)
    session_id = prov.json()["session_id"]
    resp = client.get(f"/lab-sessions/{session_id}/security-plan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["namespace"] is not None
    assert data["quota_profile"] == "standard"


# --- Branding endpoints ---

def test_api_can_list_branding_profiles(client):
    resp = client.get("/branding-profiles")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_api_can_get_branding_profile(client):
    resp = client.get("/branding-profiles/redhat-intel-default")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Partner AI Launchpad"


def test_api_branding_profile_not_found(client):
    resp = client.get("/branding-profiles/nonexistent")
    assert resp.status_code == 404
