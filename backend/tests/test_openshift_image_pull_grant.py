"""Non-live proof of the cross-namespace image-pull grant boundary."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from app.domain.models import CatalogItem, LabRequest
from kubernetes.client.exceptions import ApiException

ROOT = Path(__file__).resolve().parents[2]


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


@pytest.mark.parametrize(
    "catalog_id",
    ("intel-llm-cpu-serving", "intel-xeon6-agent-201", "multi-agent-quickstart"),
)
def test_deployed_cluster_images_and_pilot_catalog_preserve_grant_boundary(
    catalog_id: str,
) -> None:
    overlay = yaml.safe_load(
        (ROOT / "deploy/launchpad/overlays/arena/arena-clusters.yaml").read_text()
    )
    clusters = yaml.safe_load(overlay["data"]["clusters.yaml"])["clusters"]
    targets = {cluster["cluster_id"]: cluster for cluster in clusters}
    item = CatalogItem.model_validate(
        yaml.safe_load((ROOT / "catalog" / catalog_id / "catalog-item.yaml").read_text())
    )
    request = LabRequest(
        tenant_id="test-tenant",
        requester_id="test-user",
        catalog_item_id=item.catalog_item_id,
        requested_mode=item.category,
    )

    for cluster_id, expected_grant in (("arena", True), ("brutus", True), ("flightpath", False)):
        adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
        adapter._overlay_path = "/tmp/demo"
        adapter._target = SimpleNamespace(
            cluster_id=cluster_id,
            image_references=targets[cluster_id]["image_references"],
        )
        adapter._select_workshop_node_name = MagicMock(return_value="")

        plan = adapter.create_plan(request, item)

        assert adapter._requires_image_pull_grant(plan.required_resources) is expected_grant

    if catalog_id == "multi-agent-quickstart":
        chart_templates = ROOT / "deploy/workloads/multi-agent-seat/templates"
        for template in chart_templates.glob("*.yaml"):
            for line in template.read_text().splitlines():
                if line.strip().startswith("image:"):
                    assert 'include "multiAgent.image"' in line, template


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
