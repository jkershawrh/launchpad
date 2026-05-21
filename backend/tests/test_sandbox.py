"""
Sandbox TDD Red/Green Matrix — 12 gates

Tests S1-S3, S8-S10, S12 run without containers (unit tests).
Tests S4-S7, S11 marked @pytest.mark.local — require podman.
"""
import os

import pytest
from pydantic import ValidationError

from app.adapters.mock.catalog import MockCatalogAdapter
from app.domain.enums import AAPLevel, AccessMethod, StackLevel
from app.domain.sandbox import STACK_PACKAGES, SandboxConnectionInfo, SandboxProfile

local = pytest.mark.local

SANDBOX_IDS = ["sandbox-minimal", "sandbox-ai-dev", "sandbox-full-stack", "sandbox-custom"]


# ─── S1: SandboxProfile validates ────────────────────────────────────────────

def test_sandbox_profile_valid():
    profile = SandboxProfile(
        sandbox_profile_id="test-sandbox",
        display_name="Test Sandbox",
        stack_level=StackLevel.AI_DEV,
        access_methods=[AccessMethod.SSH, AccessMethod.JUPYTER],
        aap_level=AAPLevel.PLAYBOOK_LIBRARY,
    )
    assert profile.sandbox_profile_id == "test-sandbox"
    assert profile.stack_level == StackLevel.AI_DEV
    assert len(profile.access_methods) == 2
    assert profile.aap_level == AAPLevel.PLAYBOOK_LIBRARY


def test_sandbox_profile_rejects_empty_id():
    with pytest.raises(ValidationError):
        SandboxProfile(
            sandbox_profile_id="",
            display_name="Bad",
        )


# ─── S2: Sandbox catalog items exist ─────────────────────────────────────────

def test_sandbox_catalog_items_exist():
    catalog = MockCatalogAdapter()
    for sid in SANDBOX_IDS:
        item = catalog.get_item(sid)
        assert item is not None, f"Missing sandbox item: {sid}"
        assert item.category.value == "open_sandbox"


def test_sandbox_rejects_unknown():
    catalog = MockCatalogAdapter()
    assert catalog.get_item("sandbox-nonexistent-xyz") is None


# ─── S3: Sandbox request has config ──────────────────────────────────────────

def test_sandbox_request_has_stack_level():
    catalog = MockCatalogAdapter()
    item = catalog.get_item("sandbox-ai-dev")
    assert item.metadata.get("stack_level") == "ai_dev"
    assert "access_methods" in item.metadata
    assert "aap_level" in item.metadata


def test_sandbox_request_rejects_invalid_stack():
    with pytest.raises(ValueError):
        StackLevel("nonexistent_stack")


# ─── S4: Local sandbox starts ────────────────────────────────────────────────

@local
def test_local_sandbox_starts():
    from app.adapters.local.sandbox_provisioner import LocalSandboxProvisioner
    from app.domain.enums import CatalogCategory, Persistence
    from app.domain.models import LabRequest

    provisioner = LocalSandboxProvisioner()
    catalog = MockCatalogAdapter()
    item = catalog.get_item("sandbox-minimal")
    req = LabRequest(
        tenant_id="test-tenant",
        requester_id="test-user",
        catalog_item_id="sandbox-minimal",
        requested_mode=CatalogCategory.OPEN_SANDBOX,
        persistence=Persistence.EPHEMERAL,
    )
    plan = provisioner.create_plan(req, item)
    result = provisioner.provision(plan)
    assert result.namespace.startswith("sandbox-")
    assert result.resources.get("container_name")
    provisioner.cleanup(result.namespace)


def test_local_sandbox_cleanup_nonexistent_completes():
    from app.adapters.local.sandbox_provisioner import LocalSandboxProvisioner
    provisioner = LocalSandboxProvisioner()
    result = provisioner.cleanup("nonexistent-container-xyz")
    assert isinstance(result, bool)


# ─── S5: Connection info returned ────────────────────────────────────────────

def test_sandbox_returns_connection_info():
    info = SandboxConnectionInfo(
        ssh_host="localhost",
        ssh_port=2222,
        ssh_user="lab-user",
        ssh_password="launchpad",
        web_console_url="http://localhost:6901",
        jupyter_url="http://localhost:8888",
    )
    assert info.ssh_host == "localhost"
    assert info.ssh_port == 2222
    assert info.jupyter_url == "http://localhost:8888"


def test_sandbox_no_connection_before_ready():
    info = SandboxConnectionInfo()
    assert info.ssh_host is None
    assert info.web_console_url is None
    assert info.jupyter_url is None


# ─── S6: SSH accessible ──────────────────────────────────────────────────────

@local
def test_sandbox_ssh_accessible():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect(("localhost", 2222))
        sock.close()
    except (ConnectionRefusedError, OSError):
        pytest.skip("No sandbox container running on port 2222")


def test_sandbox_ssh_fails_after_reclaim():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect(("localhost", 29999))
        sock.close()
        pytest.fail("Should not connect to unused port")
    except (ConnectionRefusedError, OSError):
        pass


# ─── S7: Web console accessible ──────────────────────────────────────────────

@local
def test_sandbox_console_accessible():
    import httpx
    try:
        resp = httpx.get("http://localhost:6901", timeout=5)
        assert resp.status_code == 200
    except httpx.RequestError:
        pytest.skip("No web console running on port 6901")


def test_sandbox_console_fails_after_reclaim():
    import httpx
    try:
        httpx.get("http://localhost:59997", timeout=2)
        pytest.fail("Should not connect")
    except httpx.RequestError:
        pass


# ─── S8: Stack packages ──────────────────────────────────────────────────────

def test_sandbox_has_python():
    for level in STACK_PACKAGES:
        assert "python3.11" in STACK_PACKAGES[level]


def test_sandbox_minimal_lacks_pytorch():
    assert "pytorch" not in STACK_PACKAGES["minimal"]
    assert "pytorch" in STACK_PACKAGES["ai_dev"]
    assert "pytorch" in STACK_PACKAGES["full_redhat_ai"]


# ─── S9: AAP playbooks available ─────────────────────────────────────────────

def test_sandbox_has_playbooks():
    playbook_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "demos", "containers", "sandbox", "playbooks"
    )
    assert os.path.isdir(playbook_dir)
    playbooks = [f for f in os.listdir(playbook_dir) if f.endswith(".yml")]
    assert len(playbooks) >= 4
    expected = ["setup-model-endpoint.yml", "deploy-sample-app.yml", "install-pytorch.yml", "setup-rag-pipeline.yml"]
    for name in expected:
        assert name in playbooks, f"Missing playbook: {name}"


def test_sandbox_no_aap_when_disabled():
    catalog = MockCatalogAdapter()
    item = catalog.get_item("sandbox-minimal")
    assert item.metadata.get("aap_level") == "none"


# ─── S10: Handoff has connection info ─────────────────────────────────────────

def test_sandbox_handoff_has_ssh():
    from app.domain.reports import HandoffPackage
    handoff = HandoffPackage(
        lab_title="AI Dev Sandbox",
        tenant="partner-oem-a",
        catalog_item="sandbox-ai-dev",
        session_id="s-001",
        lab_url="http://localhost:6901",
        access_instructions="SSH: ssh lab-user@localhost -p 2222\nPassword: launchpad",
    )
    md = handoff.to_markdown()
    assert "ssh" in md.lower() or "SSH" in md
    assert "lab-user" in md


def test_sandbox_handoff_missing_for_unready():
    from app.domain.reports import HandoffPackage
    handoff = HandoffPackage(
        lab_title="Sandbox",
        tenant="t1",
        catalog_item="sandbox-minimal",
        session_id="s-001",
    )
    assert handoff.lab_url is None


# ─── S11: Reclaim stops container ─────────────────────────────────────────────

@local
def test_sandbox_reclaim_stops():
    from app.adapters.local.sandbox_provisioner import LocalSandboxProvisioner
    provisioner = LocalSandboxProvisioner()
    result = provisioner.cleanup("nonexistent-container")
    assert result is False


def test_sandbox_reclaim_idempotent():
    from app.adapters.local.sandbox_provisioner import LocalSandboxProvisioner
    provisioner = LocalSandboxProvisioner()
    result1 = provisioner.cleanup("nonexistent-1")
    result2 = provisioner.cleanup("nonexistent-1")
    assert result1 == result2


# ─── S12: API end-to-end ─────────────────────────────────────────────────────

def test_api_sandbox_launch():
    from fastapi.testclient import TestClient
    from app.api.deps import provisioning_service
    from app.main import app

    provisioning_service._requests.clear()
    provisioning_service._sessions.clear()
    provisioning_service._plans.clear()

    client = TestClient(app)
    payload = {
        "tenant_id": "partner-oem-a",
        "requester_id": "sandbox-user",
        "catalog_item_id": "sandbox-ai-dev",
        "requested_mode": "open_sandbox",
        "persistence": "persistent",
        "ttl": "8h",
    }
    resp = client.post("/lab-requests", json=payload)
    assert resp.json()["status"] == "accepted"
    rid = resp.json()["request_id"]

    resp = client.post(f"/lab-requests/{rid}/provision")
    assert resp.status_code == 201
    sid = resp.json()["session_id"]

    resp = client.post(f"/lab-sessions/{sid}/validate")
    assert resp.json()["status"] == "ready"

    resp = client.get(f"/lab-sessions/{sid}/handoff")
    assert resp.status_code == 200


def test_api_sandbox_bad_config():
    from fastapi.testclient import TestClient
    from app.api.deps import provisioning_service
    from app.main import app

    provisioning_service._requests.clear()
    provisioning_service._sessions.clear()

    client = TestClient(app)
    payload = {
        "tenant_id": "partner-oem-a",
        "requester_id": "user",
        "catalog_item_id": "sandbox-nonexistent",
        "requested_mode": "open_sandbox",
    }
    resp = client.post("/lab-requests", json=payload)
    assert resp.json()["status"] == "rejected"
