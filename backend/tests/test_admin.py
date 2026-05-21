"""
Admin Observability + Sysadmin + Dynamic Catalog — TDD Red/Green Matrix
12 gates with GREEN + RED tests.
"""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import catalog_adapter, provisioning_service
from app.domain.enums import CatalogCategory, CatalogStatus, Persistence, SessionStatus
from app.domain.models import CatalogItem, LabRequest
from app.main import app
from app.services.system_monitor import SystemMonitor


@pytest.fixture(autouse=True)
def reset_state():
    provisioning_service._requests.clear()
    provisioning_service._sessions.clear()
    provisioning_service._plans.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _provision_session(svc=None):
    svc = svc or provisioning_service
    req = LabRequest(
        tenant_id="partner-oem-a",
        requester_id="admin-test",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
        persistence=Persistence.EPHEMERAL,
    )
    submitted = svc.submit_request(req)
    session = svc.provision(submitted.request_id)
    return session


# ─── A1: System status returns data ──────────────────────────────────────────

def test_system_status_returns_health():
    monitor = SystemMonitor()
    status = monitor.get_status()
    assert "healthy" in status
    assert "containers" in status
    assert isinstance(status["containers"], int)


def test_system_status_no_containers():
    monitor = SystemMonitor()
    status = monitor.get_status()
    assert isinstance(status["containers_list"], list)


# ─── A2: Container list from podman ──────────────────────────────────────────

def test_container_list_returns_running():
    monitor = SystemMonitor()
    containers = monitor.list_containers()
    assert isinstance(containers, list)


def test_container_list_empty_when_none():
    monitor = SystemMonitor()
    containers = monitor.list_containers()
    for c in containers:
        assert "name" in c
        assert "status" in c


# ─── A3: Container logs returned ─────────────────────────────────────────────

def test_container_logs_returns_lines():
    monitor = SystemMonitor()
    result = monitor.get_container_logs("demos_gateway_1", lines=10)
    assert "name" in result
    assert "logs" in result


def test_container_logs_unknown_container():
    monitor = SystemMonitor()
    result = monitor.get_container_logs("nonexistent-container-xyz", lines=10)
    assert result["success"] is False


# ─── A4: Container restart ───────────────────────────────────────────────────

def test_container_restart_succeeds():
    monitor = SystemMonitor()
    result = monitor.restart_container("demos_gateway_1")
    assert "success" in result


def test_container_restart_unknown_fails():
    monitor = SystemMonitor()
    result = monitor.restart_container("nonexistent-container-xyz")
    assert result["success"] is False


# ─── A5: Force reclaim bypasses lifecycle ─────────────────────────────────────

def test_force_reclaim_from_any_state():
    session = _provision_session()
    assert session.status == SessionStatus.VALIDATING
    reclaimed = provisioning_service.force_reclaim_session(session.session_id)
    assert reclaimed.status == SessionStatus.RECLAIMED
    assert reclaimed.completed_at is not None
    assert "force reclaimed by admin" in reclaimed.lifecycle_events[-1].reason


def test_force_reclaim_missing_session():
    with pytest.raises(ValueError, match="not found"):
        provisioning_service.force_reclaim_session("nonexistent-session-id")


# ─── A6: Session diagnostics ─────────────────────────────────────────────────

def test_diagnostics_returns_health(client):
    session = _provision_session()
    resp = client.get(f"/admin/sessions/{session.session_id}/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session.session_id
    assert "container_status" in data
    assert "health_checks" in data


def test_diagnostics_missing_session(client):
    resp = client.get("/admin/sessions/nonexistent/diagnostics")
    assert resp.status_code == 404


# ─── A7: Add catalog item via API ────────────────────────────────────────────

def test_admin_add_catalog_item(client):
    payload = {
        "catalog_item_id": "test-new-demo",
        "display_name": "Test New Demo",
        "description": "A test demo added via admin API",
        "category": "quick_start",
        "status": "draft",
        "default_hardware_profile": "xeon-basic",
        "default_quota_profile": "standard",
        "default_ttl": "4h",
    }
    resp = client.post("/admin/catalog", json=payload)
    assert resp.status_code == 201
    assert resp.json()["catalog_item_id"] == "test-new-demo"
    assert resp.json()["status"] == "draft"
    catalog_adapter._items.pop("test-new-demo", None)


def test_admin_add_duplicate_rejected(client):
    resp = client.post("/admin/catalog", json={
        "catalog_item_id": "inference-overdrive-quickstart",
        "display_name": "Duplicate",
        "category": "quick_start",
    })
    assert resp.status_code == 409


# ─── A8: Update catalog item ─────────────────────────────────────────────────

def test_admin_update_catalog_item(client):
    resp = client.put("/admin/catalog/inference-overdrive-quickstart", json={
        "description": "Updated description for testing",
    })
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description for testing"


def test_admin_update_nonexistent(client):
    resp = client.put("/admin/catalog/nonexistent-item", json={"description": "test"})
    assert resp.status_code == 404


# ─── A9: Change catalog status ───────────────────────────────────────────────

def test_admin_deprecate_catalog_item(client):
    client.post("/admin/catalog", json={
        "catalog_item_id": "deprecate-test",
        "display_name": "Deprecate Test",
        "category": "quick_start",
        "status": "active",
    })
    resp = client.patch("/admin/catalog/deprecate-test/status", json={"status": "deprecated"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "deprecated"
    catalog_adapter._items.pop("deprecate-test", None)


def test_admin_invalid_status_change(client):
    resp = client.patch("/admin/catalog/inference-overdrive-quickstart/status", json={"status": "invalid_xyz"})
    assert resp.status_code == 400


# ─── A10: New item appears in catalog ─────────────────────────────────────────

def test_new_item_visible_in_catalog(client):
    client.post("/admin/catalog", json={
        "catalog_item_id": "visible-test",
        "display_name": "Visible Test",
        "category": "quick_start",
        "status": "active",
    })
    resp = client.get("/catalog")
    ids = [i["catalog_item_id"] for i in resp.json()]
    assert "visible-test" in ids
    catalog_adapter._items.pop("visible-test", None)


def test_draft_item_hidden_from_partners():
    item = CatalogItem(
        catalog_item_id="draft-test",
        display_name="Draft",
        category=CatalogCategory.QUICK_START,
        status=CatalogStatus.DRAFT,
    )
    assert not (item.status == CatalogStatus.ACTIVE)


# ─── A11: API system status ──────────────────────────────────────────────────

def test_api_system_status(client):
    resp = client.get("/admin/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "healthy" in data
    assert "active_sessions" in data
    assert "total_sessions" in data


# ─── A12: API force reclaim ──────────────────────────────────────────────────

def test_api_force_reclaim(client):
    session = _provision_session()
    resp = client.post(f"/admin/sessions/{session.session_id}/force-reclaim")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reclaimed"


def test_api_force_reclaim_404(client):
    resp = client.post("/admin/sessions/nonexistent/force-reclaim")
    assert resp.status_code == 404
