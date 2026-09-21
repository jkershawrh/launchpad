"""Non-live proof of the cross-namespace image-pull grant boundary."""

from unittest.mock import MagicMock

import pytest
from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from kubernetes.client.exceptions import ApiException


def _external_operator_resources() -> dict:
    return {
        "operator_workshop": True,
        "showroom_enabled": True,
        "showroom_support_images": {
            "showroom_terminal": "quay.io/example/terminal@sha256:" + "a" * 64,
            "showroom_git_cloner": "quay.io/example/cloner@sha256:" + "b" * 64,
        },
        "workload_enabled": True,
        "workload_deploy_path": "deploy/workloads/multi-agent-seat",
        "workload_helm_values": {
            "image": {"repository": "quay.io/example/agent", "digest": "sha256:" + "c" * 64}
        },
    }


def test_external_operator_images_do_not_request_internal_registry_grant() -> None:
    resources = _external_operator_resources()
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._grant_image_pull = MagicMock()

    assert adapter._requires_image_pull_grant(resources) is False
    adapter._ensure_image_pull_access("launchpad-seat", resources)

    adapter._grant_image_pull.assert_not_called()


def test_internal_images_and_unknown_workload_images_require_grant() -> None:
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._grant_image_pull = MagicMock()
    resources = _external_operator_resources()
    resources["showroom_support_images"]["showroom_terminal"] = (
        "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/terminal"
    )

    assert adapter._requires_image_pull_grant(resources) is True
    adapter._ensure_image_pull_access("launchpad-seat", resources)
    adapter._grant_image_pull.assert_called_once_with("launchpad-seat")

    resources = _external_operator_resources()
    resources["workload_helm_values"] = {}
    assert adapter._requires_image_pull_grant(resources) is True
    resources = _external_operator_resources()
    resources["workload_deploy_path"] = "deploy/workloads/other-chart"
    assert adapter._requires_image_pull_grant(resources) is True
    resources = _external_operator_resources()
    resources["showroom_support_images"].pop("showroom_terminal")
    assert adapter._requires_image_pull_grant(resources) is True
    assert adapter._requires_image_pull_grant({"operator_workshop": False}) is True


def test_unexpected_image_pull_grant_failure_is_not_suppressed() -> None:
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._rbac_v1 = MagicMock()
    adapter._rbac_v1.create_namespaced_role_binding.side_effect = ApiException(
        status=403, reason="Forbidden"
    )

    with pytest.raises(ApiException) as exc:
        adapter._grant_image_pull("launchpad-seat")

    assert exc.value.status == 403


def test_existing_image_pull_grant_remains_idempotent() -> None:
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._rbac_v1 = MagicMock()
    adapter._rbac_v1.create_namespaced_role_binding.side_effect = ApiException(
        status=409, reason="AlreadyExists"
    )

    adapter._grant_image_pull("launchpad-seat")
