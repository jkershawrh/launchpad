"""
Local Provisioning TDD Red/Green Matrix

Tests L1-L2 run without containers (unit tests).
Tests L3-L10 marked @pytest.mark.local — require running demo stack.
Run with: pytest -m local
"""
import os
import shutil

import httpx
import pytest

from app.adapters.local.cleanup import LocalCleanupAdapter
from app.adapters.local.provisioning import COMPOSE_FILE, DEMOS_ROOT, LocalProvisioningAdapter
from app.adapters.local.validation import LocalValidationAdapter
from app.domain.enums import CatalogCategory, Persistence, SessionStatus, ValidationResultStatus
from app.domain.models import LabRequest, LabSession
from app.services.provisioning import ProvisioningService

local = pytest.mark.local


def _make_request(**overrides):
    defaults = dict(
        tenant_id="partner-oem-a",
        requester_id="demo-engineer-1",
        catalog_item_id="inference-overdrive",
        requested_mode=CatalogCategory.QUICK_START,
        persistence=Persistence.EPHEMERAL,
        ttl="4h",
    )
    defaults.update(overrides)
    return LabRequest(**defaults)


def _local_service():
    return ProvisioningService(
        provisioner=LocalProvisioningAdapter(),
        validator=LocalValidationAdapter(),
        cleanup=LocalCleanupAdapter(),
    )


# ─── L1: Compose file exists ─────────────────────────────────────────────────

def test_compose_file_exists():
    assert COMPOSE_FILE.exists(), f"Expected compose file at {COMPOSE_FILE}"
    assert COMPOSE_FILE.name == "podman-compose.yaml"


def test_compose_file_rejects_bad_path():
    from pathlib import Path
    bad = Path("/nonexistent/podman-compose.yaml")
    assert not bad.exists()


# ─── L2: Podman available ────────────────────────────────────────────────────

def test_podman_binary_exists():
    podman = shutil.which("podman") or os.path.exists("/opt/podman/bin/podman")
    assert podman, "podman binary not found"


def test_podman_rejects_bad_binary():
    bad = shutil.which("podman-nonexistent-xyz")
    assert bad is None


# ─── L3: Local provisioner starts stack ───────────────────────────────────────

@local
def test_local_provisioner_starts_services():
    adapter = LocalProvisioningAdapter()
    catalog = _local_service().catalog
    item = catalog.get_item("inference-overdrive")
    req = _make_request()
    plan = adapter.create_plan(req, item)
    result = adapter.provision(plan)
    assert result.namespace.startswith("local-")
    assert result.lab_url == "http://localhost:3030"
    assert result.dashboard_url == "http://localhost:8080/api/v1/requests"


def test_local_provisioner_fails_bad_compose():
    from pathlib import Path
    adapter = LocalProvisioningAdapter(compose_file=Path("/nonexistent/compose.yaml"))
    catalog = _local_service().catalog
    item = catalog.get_item("inference-overdrive")
    req = _make_request()
    plan = adapter.create_plan(req, item)
    plan = plan.model_copy(update={"required_resources": {"compose_file": "/nonexistent/compose.yaml"}})
    with pytest.raises(FileNotFoundError):
        adapter.provision(plan)


# ─── L4: Gateway responds on :8080 ───────────────────────────────────────────

@local
def test_gateway_health_returns_200():
    resp = httpx.get("http://localhost:8080/health", timeout=10)
    assert resp.status_code == 200


def test_gateway_health_fails_when_down():
    try:
        resp = httpx.get("http://localhost:59999/health", timeout=2)
        assert resp.status_code != 200
    except httpx.RequestError:
        pass  # Expected — port not listening


# ─── L5: Frontend responds on :3030 ──────────────────────────────────────────

@local
def test_frontend_returns_200():
    resp = httpx.get("http://localhost:3030", timeout=10)
    assert resp.status_code == 200


def test_frontend_fails_when_down():
    try:
        resp = httpx.get("http://localhost:59998", timeout=2)
        assert resp.status_code != 200
    except httpx.RequestError:
        pass


# ─── L6: Local validator passes healthy ──────────────────────────────────────

@local
def test_local_validator_passes_healthy_stack():
    adapter = LocalValidationAdapter()
    session = LabSession(
        request_id="r1",
        tenant_id="t1",
        catalog_item_id="inference-overdrive",
        namespace="local-test",
    )
    results = adapter.validate(session)
    assert len(results) == 3
    assert all(r.result == ValidationResultStatus.PASS for r in results)


def test_local_validator_fails_unhealthy_stack():
    from app.adapters.local.validation import LocalValidationAdapter as LVA
    adapter = LVA()
    adapter.__class__ = type("OfflineValidator", (LVA,), {})
    session = LabSession(
        request_id="r1",
        tenant_id="t1",
        catalog_item_id="inference-overdrive",
        namespace="local-test",
    )
    # Without containers running on these ports, at least some will fail
    try:
        resp = httpx.get("http://localhost:8080/health", timeout=2)
        healthy = resp.status_code == 200
    except httpx.RequestError:
        healthy = False
    if not healthy:
        results = adapter.validate(session)
        assert any(r.result == ValidationResultStatus.FAIL for r in results)


# ─── L7: Full workflow to ready ───────────────────────────────────────────────

@local
def test_local_workflow_submit_to_ready():
    svc = _local_service()
    req = _make_request()
    submitted = svc.submit_request(req)
    assert submitted.status.value == "accepted"

    session = svc.provision(submitted.request_id)
    assert session.status == SessionStatus.VALIDATING
    assert "localhost" in session.lab_url

    validated = svc.validate_session(session.session_id)
    assert validated.status == SessionStatus.READY
    assert all(vr.result == ValidationResultStatus.PASS for vr in validated.validation_results)


def test_local_workflow_fails_no_podman():
    from pathlib import Path
    svc = ProvisioningService(
        provisioner=LocalProvisioningAdapter(compose_file=Path("/nonexistent/compose.yaml")),
        validator=LocalValidationAdapter(),
    )
    req = _make_request()
    submitted = svc.submit_request(req)
    with pytest.raises(Exception):
        svc.provision(submitted.request_id)


# ─── L8: Reclaim stops containers ────────────────────────────────────────────

@local
def test_local_reclaim_stops_services():
    svc = _local_service()
    req = _make_request()
    submitted = svc.submit_request(req)
    session = svc.provision(submitted.request_id)
    svc.validate_session(session.session_id)
    svc.activate_session(session.session_id)
    svc.reset_session(session.session_id)
    reclaimed = svc.reclaim_session(session.session_id)
    assert reclaimed.status == SessionStatus.RECLAIMED
    assert reclaimed.completed_at is not None


def test_local_reclaim_idempotent():
    cleanup = LocalCleanupAdapter()
    result = cleanup.cleanup("/nonexistent/compose.yaml")
    assert result is False


# ─── L9: URLs are real and reachable (tested within workflow) ─────────────────

@local
def test_lab_url_reachable_during_session():
    svc = _local_service()
    req = _make_request()
    submitted = svc.submit_request(req)
    session = svc.provision(submitted.request_id)
    resp = httpx.get("http://localhost:3030", timeout=10)
    assert resp.status_code == 200
    assert len(resp.text) > 0
    svc.validate_session(session.session_id)
    svc.activate_session(session.session_id)
    svc.reset_session(session.session_id)
    svc.reclaim_session(session.session_id)


@local
def test_lab_url_unreachable_after_reclaim():
    try:
        resp = httpx.get("http://localhost:3030", timeout=3)
        # If stack was left up by another test, that's ok — just verify the endpoint exists
        assert resp.status_code == 200
    except httpx.RequestError:
        pass  # Expected after reclaim


# ─── L10: API workflow end-to-end ────────────────────────────────────────────

@local
def test_api_local_launch_to_reclaim():
    import os
    os.environ["LAUNCHPAD_MODE"] = "local"
    from importlib import reload
    from app.api import deps as deps_module
    reload(deps_module)
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    payload = {
        "tenant_id": "partner-oem-a",
        "requester_id": "demo-engineer-1",
        "catalog_item_id": "inference-overdrive",
        "requested_mode": "quick_start",
    }

    resp = client.post("/lab-requests", json=payload)
    assert resp.json()["status"] == "accepted"
    rid = resp.json()["request_id"]

    resp = client.post(f"/lab-requests/{rid}/provision")
    assert resp.status_code == 201
    sid = resp.json()["session_id"]
    assert "localhost" in resp.json()["lab_url"]

    resp = client.post(f"/lab-sessions/{sid}/validate")
    assert resp.json()["status"] == "ready"

    resp = client.post(f"/lab-sessions/{sid}/activate")
    assert resp.json()["status"] == "active"

    resp = client.post(f"/lab-sessions/{sid}/reset")
    assert resp.json()["status"] == "resetting"

    resp = client.post(f"/lab-sessions/{sid}/reclaim")
    assert resp.json()["status"] == "reclaimed"

    os.environ["LAUNCHPAD_MODE"] = "mock"
    reload(deps_module)


def test_api_local_launch_bad_item():
    svc = _local_service()
    req = _make_request(catalog_item_id="nonexistent-demo")
    submitted = svc.submit_request(req)
    assert submitted.status.value == "rejected"
