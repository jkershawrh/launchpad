import threading
from unittest.mock import Mock

from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter


def test_existing_tenant_gateway_is_reconciled_without_recreating_namespace() -> None:
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._gateway_bootstrap_lock = threading.Lock()
    adapter._namespace_exists = Mock(side_effect=[False, True])
    adapter._create_namespace = Mock()
    adapter._grant_remote_control_plane_access = Mock()
    adapter._ensure_image_pull_access = Mock()
    adapter._create_demo_secrets = Mock()
    adapter._apply_kustomize = Mock()
    adapter._wait_for_deployments = Mock()

    for _ in range(2):
        adapter._ensure_tenant_gateway(
            "launchpad-gw-flightpath-candidate-cert",
            {"tenant_id": "flightpath-candidate-cert"},
            "",
        )

    adapter._create_namespace.assert_called_once()
    adapter._grant_remote_control_plane_access.assert_called_once()
    adapter._create_demo_secrets.assert_called_once()
    assert adapter._ensure_image_pull_access.call_count == 2
    assert adapter._apply_kustomize.call_count == 2
    assert adapter._wait_for_deployments.call_count == 2
