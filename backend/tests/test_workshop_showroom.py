"""TDD tests for showroom multi-user workshop enhancements."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

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
    def test_ready_workshop_has_validated_ready_sessions(self):
        """A workshop must not report ready while its sessions are validating."""
        svc = _make_service()
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=2,
            ttl="4h",
        )

        result = svc.provision_workshop(workshop)

        assert result.status == "ready"
        sessions = [svc.get_session(session_id) for session_id in result.session_ids]
        assert all(session.status == "ready" for session in sessions)
        assert all(session.validation_results for session in sessions)

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
        """Reject oversized orders instead of silently dropping requested seats."""
        svc = _make_service(max_workshop=3)
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=5,
            ttl="4h",
        )
        with patch.dict(os.environ, {"MAX_ACTIVE_SESSIONS_PER_WORKSHOP": "3"}, clear=False):
            with pytest.raises(ValueError, match="supported limit of 3"):
                svc.provision_workshop(workshop)


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
    def _node(
        cpu="10", memory="20Gi", pods="100", *, name="worker-1",
        ready=True, taints=None, labels=None, ready_for_seconds=3600,
    ):
        node = MagicMock()
        node.metadata.name = name
        node.metadata.labels = labels or {}
        node.status.allocatable = {"cpu": cpu, "memory": memory, "pods": pods}
        node.status.conditions = [
            SimpleNamespace(
                type="Ready",
                status="True" if ready else "False",
                last_transition_time=(
                    datetime.now(timezone.utc)
                    - timedelta(seconds=ready_for_seconds)
                ),
            ),
            SimpleNamespace(type="MemoryPressure", status="False"),
            SimpleNamespace(type="DiskPressure", status="False"),
            SimpleNamespace(type="PIDPressure", status="False"),
        ]
        node.spec.unschedulable = False
        node.spec.taints = taints or []
        return node

    @staticmethod
    def _pod(phase="Running", cpu="0", memory="0", node="worker-1"):
        pod = MagicMock()
        pod.status.phase = phase
        container = MagicMock()
        container.resources.requests = {"cpu": cpu, "memory": memory}
        pod.spec.containers = [container]
        pod.spec.node_name = node
        return pod

    def test_resource_estimate_adds_shared_and_bounded_transient_workshop_costs(self):
        metadata = {
            "seat_cpu_millicores": 500,
            "seat_memory_mib": 512,
            "seat_pods": 3,
            "seat_transient_cpu_millicores": 100,
            "seat_transient_memory_mib": 64,
            "seat_transient_pods": 4,
            "workshop_shared_cpu_millicores": 1000,
            "workshop_shared_memory_mib": 2048,
            "workshop_shared_pods": 9,
            "workshop_provision_concurrency": 2,
        }

        estimate = ProvisioningService._workshop_resource_estimate(metadata, 25)

        assert estimate == {
            "cpu_millicores": 13_700,
            "memory_mib": 14_976,
            "pods": 92,
            "shared": {
                "cpu_millicores": 1000,
                "memory_mib": 2048,
                "pods": 9,
            },
            "per_seat": {
                "cpu_millicores": 500,
                "memory_mib": 512,
                "pods": 3,
            },
            "transient": {
                "concurrent_seats": 2,
                "cpu_millicores": 200,
                "memory_mib": 128,
                "pods": 8,
            },
        }

    def test_capacity_solves_fixed_plus_per_seat_instead_of_dividing_all_headroom(self):
        item = _make_catalog_item()
        item.metadata = {
            "seat_cpu_millicores": 100,
            "seat_memory_mib": 100,
            "seat_pods": 3,
            "seat_transient_pods": 4,
            "workshop_shared_pods": 9,
            "workshop_provision_concurrency": 2,
        }
        svc = _make_service(catalog_item=item)
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=25,
            ttl="4h",
        )
        with (
            patch.dict(
                os.environ,
                {
                    "LAUNCHPAD_MODE": "openshift",
                    "WORKSHOP_CAPACITY_HEADROOM_PCT": "0",
                },
                clear=False,
            ),
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api") as core_api,
        ):
            core_api.return_value.list_node.return_value.items = [
                self._node(cpu="100", memory="100Gi", pods="100")
            ]
            core_api.return_value.list_pod_for_all_namespaces.return_value.items = []

            can, reason = svc.check_workshop_capacity(workshop)

        assert can is True
        assert "support 27 seats" in reason
        assert "Pods: 27" in reason

    def test_capacity_counts_only_catalog_qualified_stable_workers(self):
        required_labels = {"launchpad.redhat.com/agentops-certified": "true"}
        item = _make_catalog_item()
        item.metadata = {
            "seat_cpu_millicores": 2500,
            "seat_memory_mib": 7168,
            "seat_pods": 17,
            "workshop_node_min_ready_seconds": 900,
            "workshop_node_required_labels": required_labels,
        }
        svc = _make_service(catalog_item=item)
        workshop = Workshop(
            tenant_id="test-tenant",
            catalog_item_id="demo-a",
            num_users=10,
            ttl="4h",
        )
        nodes = [
            self._node(
                cpu="284",
                memory="768Gi",
                pods="250",
                name="qualified-stable",
                labels=required_labels,
            ),
            self._node(
                cpu="284",
                memory="768Gi",
                pods="250",
                name="qualified-recent",
                labels=required_labels,
                ready_for_seconds=60,
            ),
            self._node(
                cpu="284",
                memory="768Gi",
                pods="250",
                name="unqualified",
            ),
        ]
        pods = [self._pod(node="qualified-stable") for _ in range(41)]
        pods += [self._pod(node="qualified-recent") for _ in range(25)]
        pods += [self._pod(node="unqualified") for _ in range(177)]

        with (
            patch.dict(
                os.environ,
                {
                    "LAUNCHPAD_MODE": "openshift",
                    "WORKSHOP_CAPACITY_HEADROOM_PCT": "20",
                },
                clear=False,
            ),
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api") as core_api,
        ):
            core_api.return_value.list_node.return_value.items = nodes
            core_api.return_value.list_pod_for_all_namespaces.return_value.items = pods
            can, reason = svc.check_workshop_capacity(workshop)

        assert can is False
        assert "supports 9" in reason
        assert "Pods: 9" in reason
        assert "Eligible nodes: 1" in reason

    def test_control_plane_and_unhealthy_nodes_do_not_inflate_capacity(self):
        item = _make_catalog_item()
        item.metadata = {
            "seat_cpu_millicores": 100,
            "seat_memory_mib": 100,
            "seat_pods": 1,
        }
        svc = _make_service(catalog_item=item)
        workshop = Workshop(
            tenant_id="test-tenant", catalog_item_id="demo-a",
            num_users=10, ttl="4h",
        )
        master_taint = SimpleNamespace(
            key="node-role.kubernetes.io/master", effect="NoSchedule"
        )
        with (
            patch.dict(os.environ, {
                "LAUNCHPAD_MODE": "openshift",
                "WORKSHOP_CAPACITY_HEADROOM_PCT": "10",
            }, clear=False),
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.client.CoreV1Api") as core_api,
        ):
            core_api.return_value.list_node.return_value.items = [
                self._node(pods="10", name="worker-1"),
                self._node(pods="1000", name="master-1", taints=[master_taint]),
                self._node(pods="1000", name="worker-down", ready=False),
            ]
            core_api.return_value.list_pod_for_all_namespaces.return_value.items = []

            can, reason = svc.check_workshop_capacity(workshop)

        assert can is False
        assert "supports 9" in reason
        assert "Pods: 9" in reason

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
        assert reason == "Capacity check unavailable"

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
