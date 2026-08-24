"""
TDD: OpenShift-specific cleanup hardening.
Fix 5: Gateway lock, Fix 6: Cleanup timeout, Fix 7: Orphaned RoleBinding.
"""
import threading
import pytest
from unittest.mock import MagicMock

from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest
from app.services.provisioning import ProvisioningService


def _svc(**kw):
    return ProvisioningService(**kw)


def _req(**kw):
    defaults = dict(
        tenant_id="cleanup-ocp-test",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(kw)
    return LabRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 5: Gateway Namespace Lock
# ═══════════════════════════════════════════════════════════════════════════════

class TestGatewayNamespaceLock:

    def test_gateway_lock_exists(self):
        """RED: ProvisioningService should have _gw_locks dict."""
        svc = _svc()
        assert hasattr(svc, "_gw_locks"), "Service must have _gw_locks for gateway namespace locking"

    def test_get_gw_lock_returns_lock(self):
        """RED: _get_gw_lock should return a threading.Lock."""
        svc = _svc()
        lock = svc._get_gw_lock("launchpad-gw-test")
        assert isinstance(lock, type(threading.Lock()))

    def test_same_gateway_returns_same_lock(self):
        """RED: same gateway namespace should return the same lock."""
        svc = _svc()
        lock1 = svc._get_gw_lock("launchpad-gw-test")
        lock2 = svc._get_gw_lock("launchpad-gw-test")
        assert lock1 is lock2

    def test_different_gateways_different_locks(self):
        """RED: different gateway namespaces should have different locks."""
        svc = _svc()
        lock1 = svc._get_gw_lock("launchpad-gw-a")
        lock2 = svc._get_gw_lock("launchpad-gw-b")
        assert lock1 is not lock2


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 6: Cleanup Timeout Fatal
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from kubernetes.client.rest import ApiException as _K8sApiException
    HAS_KUBERNETES = True
except ImportError:
    HAS_KUBERNETES = False


@pytest.mark.skipif(not HAS_KUBERNETES, reason="kubernetes package not installed")
class TestCleanupTimeoutFatal:

    def test_cleanup_timeout_error_exists(self):
        """RED: CleanupTimeoutError should be importable."""
        from app.adapters.openshift.cleanup import CleanupTimeoutError
        assert CleanupTimeoutError is not None

    def test_cleanup_timeout_raises(self):
        """RED: stuck namespace should raise CleanupTimeoutError."""
        from app.adapters.openshift.cleanup import CleanupTimeoutError, OpenShiftCleanupAdapter

        adapter = OpenShiftCleanupAdapter.__new__(OpenShiftCleanupAdapter)
        adapter._active_namespaces = {}

        mock_core = MagicMock()
        mock_ns = MagicMock()
        mock_ns.status.phase = "Terminating"
        mock_core.read_namespace.return_value = mock_ns
        mock_core.delete_namespace.return_value = None
        adapter._core_v1 = mock_core
        adapter._rbac_v1 = MagicMock()

        with pytest.raises(CleanupTimeoutError):
            adapter.cleanup("stuck-namespace", timeout=1)

    def test_default_cleanup_does_not_wait(self):
        from app.adapters.openshift.cleanup import OpenShiftCleanupAdapter

        adapter = OpenShiftCleanupAdapter.__new__(OpenShiftCleanupAdapter)
        adapter._active_namespaces = {}
        adapter._core_v1 = MagicMock()
        adapter._rbac_v1 = MagicMock()
        adapter._wait_for_deletion = MagicMock()

        assert adapter.cleanup("async-delete-namespace") is True
        adapter._core_v1.delete_namespace.assert_called_once_with(
            name="async-delete-namespace"
        )
        adapter._wait_for_deletion.assert_not_called()


@pytest.mark.skipif(not HAS_KUBERNETES, reason="kubernetes package not installed")
class TestOrphanedRoleBindingCleanup:

    def test_cleanup_deletes_role_binding(self):
        """RED: cleanup should delete the image-puller RoleBinding from parent namespace."""
        from app.adapters.openshift.cleanup import OpenShiftCleanupAdapter

        adapter = OpenShiftCleanupAdapter.__new__(OpenShiftCleanupAdapter)
        adapter._active_namespaces = {}

        mock_core = MagicMock()
        mock_rbac = MagicMock()

        mock_core.delete_namespace.return_value = None
        mock_core.read_namespace.side_effect = _K8sApiException(status=404)

        adapter._core_v1 = mock_core
        adapter._rbac_v1 = mock_rbac

        adapter.cleanup("test-demo-namespace")

        mock_rbac.delete_namespaced_role_binding.assert_called_once_with(
            name="test-demo-namespace-image-puller",
            namespace="partner-ai-launchpad",
        )

    def test_cleanup_ignores_missing_role_binding(self):
        """RED: if RoleBinding doesn't exist, cleanup should not fail."""
        from app.adapters.openshift.cleanup import OpenShiftCleanupAdapter

        adapter = OpenShiftCleanupAdapter.__new__(OpenShiftCleanupAdapter)
        adapter._active_namespaces = {}

        mock_core = MagicMock()
        mock_rbac = MagicMock()

        mock_core.delete_namespace.return_value = None
        mock_core.read_namespace.side_effect = _K8sApiException(status=404)
        mock_rbac.delete_namespaced_role_binding.side_effect = _K8sApiException(status=404)

        adapter._core_v1 = mock_core
        adapter._rbac_v1 = mock_rbac

        adapter.cleanup("test-demo-namespace")
