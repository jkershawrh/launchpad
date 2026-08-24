"""E2E integration tests for Oberon deployment — Phase 7 gate matrix.

These tests run against the mock/in-memory backend (no live cluster required).
They validate the full provision lifecycle with the FileCatalogAdapter.
"""
from __future__ import annotations

import os
import tempfile

import pytest
import yaml

from app.domain.enums import CatalogCategory, CatalogStatus, LabRequestStatus, SessionStatus
from app.domain.models import LabRequest


def _write_catalog_item(base_dir: str, name: str, data: dict) -> str:
    subdir = os.path.join(base_dir, name)
    os.makedirs(subdir, exist_ok=True)
    path = os.path.join(subdir, "catalog-item.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def _smoke_item():
    return {
        "catalog_item_id": "smoke-test",
        "display_name": "Smoke Test",
        "category": "quick_start",
        "status": "active",
        "default_hardware_profile": "xeon-basic",
        "default_quota_profile": "small",
        "default_ttl": "10m",
    }


def _bad_model_item():
    return {
        "catalog_item_id": "bad-model-demo",
        "display_name": "Bad Model Demo",
        "category": "quick_start",
        "status": "active",
        "metadata": {
            "required_models": ["nonexistent-model-xyz"],
        },
    }


def _create_service(tmp_path):
    from app.adapters.file.catalog import FileCatalogAdapter
    from app.adapters.openshift.preflight import MockPreflightAdapter
    from app.services.provisioning import ProvisioningService

    adapter = FileCatalogAdapter(str(tmp_path))
    svc = ProvisioningService(catalog=adapter)
    return svc, adapter


# ── Gate 7.1: test_catalog_lists_smoke_demo ──────────────────────────

class TestCatalogListsSmokeDemo:
    def test_smoke_demo_in_catalog(self, tmp_path):
        _write_catalog_item(str(tmp_path), "smoke-test", _smoke_item())
        svc, adapter = _create_service(tmp_path)

        items = adapter.list_items()
        ids = {i.catalog_item_id for i in items}
        assert "smoke-test" in ids


# ── Gate 7.2: test_provision_smoke_demo ──────────────────────────────

class TestProvisionSmokeDemo:
    def test_submit_and_accept(self, tmp_path):
        _write_catalog_item(str(tmp_path), "smoke-test", _smoke_item())
        svc, _ = _create_service(tmp_path)

        request = LabRequest(
            tenant_id="smoke-tenant",
            requester_id="smoke-user",
            catalog_item_id="smoke-test",
            requested_mode=CatalogCategory.QUICK_START,
        )
        result = svc.submit_request(request)
        assert result.status == LabRequestStatus.ACCEPTED


# ── Gate 7.5: test_preflight_blocks_bad_demo ─────────────────────────

class TestPreflightBlocksBadDemo:
    def test_bad_model_rejected(self, tmp_path):
        from unittest.mock import MagicMock
        from app.adapters.file.catalog import FileCatalogAdapter
        from app.adapters.openshift.preflight import PreflightCheck, PreflightResult
        from app.services.provisioning import ProvisioningService

        _write_catalog_item(str(tmp_path), "bad-model-demo", _bad_model_item())
        adapter = FileCatalogAdapter(str(tmp_path))

        mock_preflight = MagicMock()
        mock_preflight.check.return_value = PreflightResult(
            passed=False,
            checks=[PreflightCheck(name="model:nonexistent", status="fail", message="Model not found")],
        )

        svc = ProvisioningService(catalog=adapter, preflight=mock_preflight)

        request = LabRequest(
            tenant_id="test-tenant",
            requester_id="test-user",
            catalog_item_id="bad-model-demo",
            requested_mode=CatalogCategory.QUICK_START,
        )
        accepted = svc.submit_request(request)
        assert accepted.status == LabRequestStatus.ACCEPTED

        with pytest.raises(ValueError, match="(?i)preflight"):
            svc.provision(accepted.request_id)


# ── Gate 7.B1: BDD — new demo dir → auto-detected ───────────────────

class TestBDDNewDemoAutoDetected:
    def test_new_dir_detected_via_reload(self, tmp_path):
        _write_catalog_item(str(tmp_path), "original", _smoke_item())
        svc, adapter = _create_service(tmp_path)
        assert len(adapter.list_items()) == 1

        _write_catalog_item(str(tmp_path), "added-demo", {
            "catalog_item_id": "added-demo",
            "display_name": "Added Demo",
            "category": "quick_start",
            "status": "active",
        })
        adapter.reload()
        assert len(adapter.list_items()) == 2
        assert adapter.get_item("added-demo") is not None


# ── Contract: session lifecycle transitions ──────────────────────────

class TestSessionLifecycleContract:
    def test_submit_transitions_to_accepted(self, tmp_path):
        _write_catalog_item(str(tmp_path), "smoke-test", _smoke_item())
        svc, _ = _create_service(tmp_path)

        request = LabRequest(
            tenant_id="smoke-tenant",
            requester_id="smoke-user",
            catalog_item_id="smoke-test",
            requested_mode=CatalogCategory.QUICK_START,
        )
        result = svc.submit_request(request)
        assert result.status == LabRequestStatus.ACCEPTED

    def test_submit_rejects_missing_catalog_item(self, tmp_path):
        svc, _ = _create_service(tmp_path)

        request = LabRequest(
            tenant_id="smoke-tenant",
            requester_id="smoke-user",
            catalog_item_id="nonexistent",
            requested_mode=CatalogCategory.QUICK_START,
        )
        result = svc.submit_request(request)
        assert result.status == LabRequestStatus.REJECTED
