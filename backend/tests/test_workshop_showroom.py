"""TDD tests for showroom multi-user workshop enhancements."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.domain.enums import CatalogCategory, CatalogStatus, LabRequestStatus
from app.domain.models import CatalogItem, LabRequest, Workshop
from app.services.provisioning import ProvisioningService


def _make_catalog_item(item_id="demo-a", required_models=None):
    data = {
        "catalog_item_id": item_id,
        "display_name": f"Test {item_id}",
        "category": CatalogCategory.QUICK_START,
        "status": CatalogStatus.ACTIVE,
        "default_hardware_profile": "xeon-basic",
        "default_quota_profile": "standard",
        "default_ttl": "4h",
    }
    if required_models:
        data["metadata"] = {"required_models": required_models}
    return CatalogItem(**data)


def _make_service(catalog_item=None, preflight=None, max_workshop=50):
    mock_catalog = MagicMock()
    item = catalog_item or _make_catalog_item()
    mock_catalog.get_item.return_value = item
    mock_catalog.list_items.return_value = [item]

    mock_constraints = MagicMock()
    from app.adapters.interfaces import ConstraintResult
    mock_constraints.evaluate.return_value = ConstraintResult(allowed=True)

    with patch.dict(os.environ, {"MAX_ACTIVE_SESSIONS_PER_WORKSHOP": str(max_workshop)}, clear=False):
        svc = ProvisioningService(
            catalog=mock_catalog,
            constraints=mock_constraints,
            preflight=preflight,
        )
    return svc


# ── Task 8: Session limits for workshops ─────────────────────────────

class TestWorkshopSessionLimits:
    def test_workshop_bypasses_per_user_limit(self):
        """Each workshop user is unique, so per-user limit shouldn't block."""
        svc = _make_service()
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=5,
            ttl="4h",
        )
        result = svc.provision_workshop(workshop)
        assert result.status == "ready"
        assert len(result.session_ids) == 5

    def test_workshop_bypasses_default_tenant_limit(self):
        """Workshops should not be capped at MAX_ACTIVE_PER_TENANT=5."""
        with patch.dict(os.environ, {"MAX_ACTIVE_SESSIONS_PER_TENANT": "5"}, clear=False):
            svc = _make_service(max_workshop=20)
            workshop = Workshop(
                tenant_id="test-tenant",
                catalog_item_id="demo-a",
                num_users=10,
                ttl="4h",
            )
            result = svc.provision_workshop(workshop)
            assert len(result.session_ids) == 10

    def test_workshop_respects_workshop_limit(self):
        """MAX_ACTIVE_PER_WORKSHOP caps total workshop sessions."""
        svc = _make_service(max_workshop=3)
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=5,
            ttl="4h",
        )
        with patch.dict(os.environ, {"MAX_ACTIVE_SESSIONS_PER_WORKSHOP": "3"}, clear=False):
            result = svc.provision_workshop(workshop)
        assert len(result.session_ids) == 3


# ── Task 9: Workshop handoff endpoint ────────────────────────────────

class TestWorkshopHandoff:
    def test_get_workshop_users_returns_list(self):
        svc = _make_service()
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=3,
            ttl="4h",
        )
        result = svc.provision_workshop(workshop)

        users = svc.get_workshop_users(result.workshop_id)
        assert len(users) == 3
        for user in users:
            assert "user_id" in user
            assert "lab_url" in user
            assert "status" in user
            assert "session_id" in user

    def test_get_workshop_users_not_found(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="not found"):
            svc.get_workshop_users("nonexistent")


# ── Task 10: Workshop-level preflight ────────────────────────────────

class TestWorkshopPreflight:
    def test_workshop_fails_on_preflight_failure(self):
        from app.adapters.openshift.preflight import PreflightCheck, PreflightResult

        mock_preflight = MagicMock()
        mock_preflight.check.return_value = PreflightResult(
            passed=False,
            checks=[PreflightCheck(name="model:bad", status="fail", message="Model not available")],
        )
        svc = _make_service(
            catalog_item=_make_catalog_item(required_models=["bad-model"]),
            preflight=mock_preflight,
        )

        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=5,
            ttl="4h",
        )
        result = svc.provision_workshop(workshop)
        assert result.status == "preflight_failed"
        assert len(result.session_ids) == 0

    def test_workshop_succeeds_on_preflight_pass(self):
        from app.adapters.openshift.preflight import PreflightResult

        mock_preflight = MagicMock()
        mock_preflight.check.return_value = PreflightResult(passed=True, checks=[])
        svc = _make_service(preflight=mock_preflight)

        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=3,
            ttl="4h",
        )
        result = svc.provision_workshop(workshop)
        assert result.status == "ready"
        assert len(result.session_ids) == 3

    def test_workshop_skips_preflight_when_no_preflight_adapter(self):
        svc = _make_service(preflight=None)

        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=3,
            ttl="4h",
        )
        result = svc.provision_workshop(workshop)
        assert result.status == "ready"
        assert len(result.session_ids) == 3


# ── Task 11: Capacity guard ─────────────────────────────────────────

class TestCapacityGuard:
    @staticmethod
    def _node(cpu="10", memory="20Gi", pods="100"):
        node = MagicMock()
        node.status.allocatable = {"cpu": cpu, "memory": memory, "pods": pods}
        return node

    @staticmethod
    def _pod(phase="Running", cpu="0", memory="0"):
        pod = MagicMock()
        pod.status.phase = phase
        container = MagicMock()
        container.resources.requests = {"cpu": cpu, "memory": memory}
        pod.spec.containers = [container]
        return pod

    def test_workshop_checks_capacity(self):
        svc = _make_service()
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=3,
            ttl="4h",
        )
        can, reason = svc.check_workshop_capacity(workshop)
        assert isinstance(can, bool)
        assert isinstance(reason, str)

    def test_capacity_check_returns_true_in_mock_mode(self):
        svc = _make_service()
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=3,
            ttl="4h",
        )
        can, reason = svc.check_workshop_capacity(workshop)
        assert can is True

    def test_capacity_check_fails_closed_when_cluster_read_fails(self):
        svc = _make_service()
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=3,
            ttl="4h",
        )
        with (
            patch.dict(os.environ, {"LAUNCHPAD_MODE": "openshift"}, clear=False),
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api") as core_api,
        ):
            core_api.return_value.list_node.side_effect = PermissionError("forbidden")
            can, reason = svc.check_workshop_capacity(workshop)

        assert can is False
        assert "failed" in reason.lower()

    def test_live_pod_slots_limit_workshop_capacity(self):
        item = _make_catalog_item()
        item.metadata = {
            "seat_cpu_millicores": 100,
            "seat_memory_mib": 100,
            "seat_pods": 1,
        }
        svc = _make_service(catalog_item=item)
        workshop = Workshop(
            tenant_id="test-tenant", catalog_item_id="demo-a",
            num_users=2, ttl="4h",
        )
        pods = [self._pod() for _ in range(8)]
        pods += [self._pod("Succeeded"), self._pod("Failed")]
        with (
            patch.dict(os.environ, {
                "LAUNCHPAD_MODE": "openshift",
                "WORKSHOP_CAPACITY_HEADROOM_PCT": "10",
            }, clear=False),
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api") as core_api,
        ):
            core_api.return_value.list_node.return_value.items = [self._node(pods="10")]
            core_api.return_value.list_pod_for_all_namespaces.return_value.items = pods
            can, reason = svc.check_workshop_capacity(workshop)

        assert can is False
        assert "supports 1" in reason
        assert "Pods: 1" in reason

    def test_existing_resource_requests_reduce_capacity(self):
        item = _make_catalog_item()
        item.metadata = {
            "seat_cpu_millicores": 1000,
            "seat_memory_mib": 1024,
            "seat_pods": 1,
        }
        svc = _make_service(catalog_item=item)
        workshop = Workshop(
            tenant_id="test-tenant", catalog_item_id="demo-a",
            num_users=3, ttl="4h",
        )
        pods = [self._pod(cpu="3500m", memory="2Gi")]
        with (
            patch.dict(os.environ, {
                "LAUNCHPAD_MODE": "openshift",
                "WORKSHOP_CAPACITY_HEADROOM_PCT": "20",
            }, clear=False),
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api") as core_api,
        ):
            core_api.return_value.list_node.return_value.items = [
                self._node(cpu="5", memory="8Gi", pods="100")
            ]
            core_api.return_value.list_pod_for_all_namespaces.return_value.items = pods
            can, reason = svc.check_workshop_capacity(workshop)

        assert can is False
        assert "supports 0" in reason
        assert "CPU: 0" in reason
