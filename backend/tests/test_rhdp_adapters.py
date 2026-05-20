"""
RHDP Adapter Unit Tests

Tests for the Sandbox API client, pool adapter, provisioning adapter,
validation adapter, and cleanup adapter. All API calls are mocked.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.rhdp.cleanup import RHDPCleanupAdapter
from app.adapters.rhdp.pool import RHDPPoolAdapter
from app.adapters.rhdp.provisioning import RHDPProvisioningAdapter
from app.adapters.rhdp.sandbox_api import (
    PlacementResult,
    PlacementResource,
    SandboxAPIClient,
    SandboxAPIError,
)
from app.adapters.rhdp.validation import RHDPValidationAdapter
from app.domain.enums import CatalogCategory, LabRequestStatus, SessionStatus
from app.domain.models import CatalogItem, LabRequest, LabSession


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _mock_placement_success():
    return PlacementResult(
        service_uuid="test-uuid-001",
        status="success",
        resources=[PlacementResource(
            name="sandbox-test-1",
            kind="OcpSandbox",
            status="success",
            namespace="sandbox-test-1-demo",
            ingress_domain="apps.ocpv09.rhdp.net",
            console_url="https://console-openshift-console.apps.ocpv09.rhdp.net",
            credentials=[{"kind": "ServiceAccount", "token": "sa-token-abc123"}],
            cluster_additional_vars={"deployer": {"domain": "apps.ocpv09.rhdp.net"}},
        )],
    )


def _mock_placement_initializing():
    return PlacementResult(
        service_uuid="test-uuid-001",
        status="initializing",
        resources=[PlacementResource(
            name="sandbox-test-1",
            kind="OcpSandbox",
            status="initializing",
        )],
    )


def _mock_catalog_item(**overrides):
    defaults = dict(
        catalog_item_id="inference-overdrive",
        display_name="Inference Overdrive",
        category=CatalogCategory.QUICK_START,
        metadata={
            "demo_pages": "overdrive,try-it,architecture",
            "provisioner_mode": "rhdp",
            "agnosticv_tenant_config": "launchpad-inference-overdrive-tenant",
            "agnosticv_cloud_selector": {"cloud": "cnv-dedicated-shared", "lab": "launchpad"},
        },
    )
    defaults.update(overrides)
    return CatalogItem(**defaults)


def _mock_request(**overrides):
    defaults = dict(
        tenant_id="partner-oem-a",
        requester_id="demo-user-1",
        catalog_item_id="inference-overdrive",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(overrides)
    return LabRequest(**defaults)


def _mock_session(**overrides):
    defaults = dict(
        request_id="req-001",
        tenant_id="partner-oem-a",
        catalog_item_id="inference-overdrive",
        namespace="sandbox-test-1-demo",
        status=SessionStatus.VALIDATING,
        resources={"sandbox_name": "sandbox-test-1"},
    )
    defaults.update(overrides)
    return LabSession(**defaults)


# ─── SandboxAPIClient Tests ────────────────────────────────────────────────────

class TestSandboxAPIClient:

    def test_login_exchanges_token(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="jwt-login")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "jwt-access-token",
            "access_token_exp": "2026-12-31T00:00:00Z",
        }
        with patch("requests.get", return_value=mock_resp) as mock_get:
            token = client._get_access_token()
            assert token == "jwt-access-token"
            mock_get.assert_called_once()

    def test_login_failure_raises(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="bad-token")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(SandboxAPIError) as exc_info:
                client._get_access_token()
            assert exc_info.value.status_code == 401

    def test_login_caches_token(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="jwt-login")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "cached-token", "access_token_exp": "2026-12-31"}
        with patch("requests.get", return_value=mock_resp) as mock_get:
            token1 = client._get_access_token()
            token2 = client._get_access_token()
            assert token1 == token2
            assert mock_get.call_count == 1

    def test_create_placement_success(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="jwt")
        client._access_token = "valid-token"
        client._token_exp = 9999999999
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "message": "Placement Created",
            "Placement": {
                "service_uuid": "uuid-001",
                "status": "initializing",
                "resources": [{"name": "sandbox-1", "kind": "OcpSandbox", "status": "initializing"}],
            },
        }
        with patch("requests.request", return_value=mock_resp):
            result = client.create_placement("uuid-001", [{"kind": "OcpSandbox"}])
            assert result.service_uuid == "uuid-001"
            assert result.status == "initializing"
            assert len(result.resources) == 1

    def test_create_placement_no_matching_cluster(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="jwt")
        client._access_token = "valid-token"
        client._token_exp = 9999999999
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"message": "No OCP shared cluster configuration found"}
        with patch("requests.request", return_value=mock_resp):
            with pytest.raises(SandboxAPIError) as exc_info:
                client.create_placement("uuid-001", [{"kind": "OcpSandbox", "cloud_selector": {"cannot": "schedule"}}])
            assert exc_info.value.status_code == 404
            assert "No OCP shared cluster" in exc_info.value.message

    def test_get_placement_success(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="jwt")
        client._access_token = "valid-token"
        client._token_exp = 9999999999
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "service_uuid": "uuid-001",
            "status": "success",
            "resources": [{
                "name": "sandbox-1",
                "kind": "OcpSandbox",
                "status": "success",
                "namespace": "sandbox-guid-1-demo",
                "ingress_domain": "apps.cluster.example.com",
                "console_url": "https://console-openshift-console.apps.cluster.example.com",
                "credentials": [{"kind": "ServiceAccount", "token": "sa-token-xyz"}],
            }],
        }
        with patch("requests.request", return_value=mock_resp):
            result = client.get_placement("uuid-001")
            assert result.status == "success"
            assert result.resources[0].namespace == "sandbox-guid-1-demo"
            assert result.resources[0].sa_token == "sa-token-xyz"

    def test_delete_placement_success(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="jwt")
        client._access_token = "valid-token"
        client._token_exp = 9999999999
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch("requests.request", return_value=mock_resp):
            assert client.delete_placement("uuid-001") is True

    def test_delete_placement_already_gone(self):
        client = SandboxAPIClient(api_url="https://api.test", login_token="jwt")
        client._access_token = "valid-token"
        client._token_exp = 9999999999
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("requests.request", return_value=mock_resp):
            assert client.delete_placement("uuid-001") is True

    def test_placement_resource_sa_token(self):
        resource = PlacementResource(
            name="test", kind="OcpSandbox", status="success",
            credentials=[
                {"kind": "Token", "token": "wrong"},
                {"kind": "ServiceAccount", "token": "correct-token"},
            ],
        )
        assert resource.sa_token == "correct-token"

    def test_placement_resource_no_sa_token(self):
        resource = PlacementResource(name="test", kind="OcpSandbox", status="success", credentials=[])
        assert resource.sa_token is None


# ─── RHDPPoolAdapter Tests ──────────────────────────────────────────────────────

class TestRHDPPoolAdapter:

    def test_check_capacity_always_true(self):
        adapter = RHDPPoolAdapter(sandbox_api=MagicMock())
        assert adapter.check_capacity("gaudi-endpoint", "standard") is True

    def test_reserve_creates_and_waits_for_placement(self):
        mock_api = MagicMock(spec=SandboxAPIClient)
        mock_api.create_placement.return_value = _mock_placement_initializing()
        mock_api.wait_for_placement.return_value = _mock_placement_success()

        adapter = RHDPPoolAdapter(sandbox_api=mock_api)
        result = adapter.reserve("session-001", "gaudi-endpoint", "standard")

        mock_api.create_placement.assert_called_once()
        mock_api.wait_for_placement.assert_called_once_with("session-001", timeout=300)
        assert result["namespace"] == "sandbox-test-1-demo"
        assert result["ingress_domain"] == "apps.ocpv09.rhdp.net"
        assert result["sa_token"] == "sa-token-abc123"
        assert result["sandbox_name"] == "sandbox-test-1"

    def test_reserve_failure_raises(self):
        mock_api = MagicMock(spec=SandboxAPIClient)
        mock_api.create_placement.side_effect = SandboxAPIError(404, "No OCP shared cluster configuration found")

        adapter = RHDPPoolAdapter(sandbox_api=mock_api)
        with pytest.raises(ValueError, match="Failed to reserve sandbox"):
            adapter.reserve("session-001", "gaudi-endpoint", "standard")

    def test_release_deletes_placement(self):
        mock_api = MagicMock(spec=SandboxAPIClient)
        mock_api.delete_placement.return_value = True

        adapter = RHDPPoolAdapter(sandbox_api=mock_api)
        assert adapter.release("session-001") is True
        mock_api.delete_placement.assert_called_once_with("session-001")

    def test_build_cloud_selector_gaudi(self):
        adapter = RHDPPoolAdapter(sandbox_api=MagicMock())
        selector = adapter._build_cloud_selector("gaudi-endpoint")
        assert selector == {"gaudi": "true"}

    def test_build_cloud_selector_xeon(self):
        adapter = RHDPPoolAdapter(sandbox_api=MagicMock())
        selector = adapter._build_cloud_selector("xeon-basic")
        assert selector == {}

    def test_build_cloud_selector_mixed(self):
        adapter = RHDPPoolAdapter(sandbox_api=MagicMock())
        selector = adapter._build_cloud_selector("mixed-overdrive")
        assert selector == {"gaudi": "true"}

    def test_report_allocation(self):
        mock_api = MagicMock(spec=SandboxAPIClient)
        mock_api.list_sandboxes.return_value = [{"name": "s1"}, {"name": "s2"}]

        adapter = RHDPPoolAdapter(sandbox_api=mock_api)
        report = adapter.report_allocation()
        assert report["total_sandboxes"] == 2


# ─── RHDPProvisioningAdapter Tests ──────────────────────────────────────────────

class TestRHDPProvisioningAdapter:

    def test_create_plan_with_agnosticv_config(self):
        adapter = RHDPProvisioningAdapter()
        request = _mock_request()
        catalog_item = _mock_catalog_item()

        plan = adapter.create_plan(request, catalog_item)

        assert len(plan.steps) == 1
        assert plan.steps[0].adapter == "sandbox-api"
        assert plan.steps[0].action == "noop"
        assert plan.steps[0].params["agnosticv_config"] == "launchpad-inference-overdrive-tenant"

    def test_create_plan_without_agnosticv_config(self):
        adapter = RHDPProvisioningAdapter()
        request = _mock_request()
        catalog_item = _mock_catalog_item(metadata={
            "deploy_method": "kustomize",
            "deploy_path": "demos/deploy/cluster",
            "demo_pages": "overdrive",
        })

        plan = adapter.create_plan(request, catalog_item)

        assert len(plan.steps) == 1
        assert plan.steps[0].adapter == "rhdp"
        assert plan.steps[0].action == "kustomize"
        assert plan.steps[0].params["deploy_path"] == "demos/deploy/cluster"

    def test_provision_agnosticv_managed_returns_console_url(self):
        adapter = RHDPProvisioningAdapter()
        request = _mock_request()
        catalog_item = _mock_catalog_item()
        plan = adapter.create_plan(request, catalog_item)
        plan = plan.model_copy(update={
            "required_resources": {
                "sandbox_data": {
                    "namespace": "sandbox-guid-1-demo",
                    "ingress_domain": "apps.ocpv09.rhdp.net",
                    "console_url": "https://console.apps.ocpv09.rhdp.net",
                    "sa_token": "sa-token-abc",
                    "sandbox_name": "sandbox-guid-1",
                },
            },
        })

        result = adapter.provision(plan)

        assert result.namespace == "sandbox-guid-1-demo"
        assert result.lab_url == "https://console.apps.ocpv09.rhdp.net"
        assert result.resources["provisioned_by"] == "rhdp"

    def test_infer_api_url(self):
        assert RHDPProvisioningAdapter._infer_api_url("apps.ocpv09.rhdp.net") == "https://api.ocpv09.rhdp.net:6443"
        assert RHDPProvisioningAdapter._infer_api_url("") == ""


# ─── RHDPValidationAdapter Tests ────────────────────────────────────────────────

class TestRHDPValidationAdapter:

    def test_validate_session_with_sandbox(self):
        adapter = RHDPValidationAdapter()
        session = _mock_session()

        results = adapter.validate(session)

        assert len(results) >= 2
        statuses = {r.check_name: r.result.value for r in results}
        assert statuses["sandbox-placement"] == "pass"
        assert statuses["namespace-exists"] == "pass"

    def test_validate_session_without_sandbox(self):
        adapter = RHDPValidationAdapter()
        session = _mock_session(resources={}, namespace=None)

        results = adapter.validate(session)

        statuses = {r.check_name: r.result.value for r in results}
        assert statuses["sandbox-placement"] == "fail"
        assert statuses["namespace-exists"] == "fail"

    def test_validate_session_with_lab_url(self):
        adapter = RHDPValidationAdapter()
        session = _mock_session(lab_url="https://demo.apps.ocpv09.rhdp.net")

        results = adapter.validate(session)

        statuses = {r.check_name: r.result.value for r in results}
        assert statuses["lab-url-set"] == "pass"

    def test_validate_session_without_lab_url(self):
        adapter = RHDPValidationAdapter()
        session = _mock_session()

        results = adapter.validate(session)

        check_names = [r.check_name for r in results]
        assert "lab-url-set" not in check_names


# ─── RHDPCleanupAdapter Tests ───────────────────────────────────────────────────

class TestRHDPCleanupAdapter:

    def test_cleanup_deletes_placement(self):
        mock_api = MagicMock(spec=SandboxAPIClient)
        mock_api.delete_placement.return_value = True

        adapter = RHDPCleanupAdapter(sandbox_api=mock_api)
        adapter.cleanup("session-001")
        mock_api.delete_placement.assert_called_once_with("session-001")

    def test_cleanup_already_deleted_no_error(self):
        mock_api = MagicMock(spec=SandboxAPIClient)
        mock_api.delete_placement.side_effect = SandboxAPIError(404, "Not found")

        adapter = RHDPCleanupAdapter(sandbox_api=mock_api)
        adapter.cleanup("session-001")

    def test_cleanup_other_error_raises(self):
        mock_api = MagicMock(spec=SandboxAPIClient)
        mock_api.delete_placement.side_effect = SandboxAPIError(500, "Internal error")

        adapter = RHDPCleanupAdapter(sandbox_api=mock_api)
        with pytest.raises(SandboxAPIError):
            adapter.cleanup("session-001")
