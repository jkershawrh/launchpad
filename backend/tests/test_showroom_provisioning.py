from unittest.mock import MagicMock

from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem, LabRequest


def _guided_item() -> CatalogItem:
    return CatalogItem(
        catalog_item_id="guided-rag-on-xeon",
        display_name="Guided RAG on Intel Xeon",
        category=CatalogCategory.GUIDED_BUILD,
        status=CatalogStatus.ACTIVE,
        metadata={
            "demo_pages": "try-it",
            "workspace_path": "/try-it",
            "showroom": True,
            "showroom_title": "Build a RAG Assistant",
            "showroom_steps": [
                {"title": "Inspect", "description": "Review the architecture."},
                {"title": "Test", "description": "Send a grounded prompt."},
            ],
        },
    )


def test_guided_catalog_item_adds_showroom_to_plan():
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    request = LabRequest(
        tenant_id="partner-a",
        requester_id="user-a",
        catalog_item_id="guided-rag-on-xeon",
        requested_mode=CatalogCategory.GUIDED_BUILD,
    )

    plan = adapter.create_plan(request, _guided_item())

    assert plan.required_resources["showroom_enabled"] is True
    assert plan.required_resources["showroom_title"] == "Build a RAG Assistant"
    assert len(plan.required_resources["showroom_steps"]) == 2
    assert plan.required_resources["demo_pages"] == "try-it"
    assert plan.required_resources["workspace_path"] == "/try-it"


def test_guided_workspace_deep_links_to_the_rag_experience():
    url = OpenShiftProvisioningAdapter._workspace_url(
        "https://workspace.example.test", "/try-it"
    )

    assert url == "https://workspace.example.test/try-it"


def test_showroom_is_deployed_by_gitops_not_inline_html():
    assert not hasattr(OpenShiftProvisioningAdapter, "_showroom_html")
    assert not hasattr(OpenShiftProvisioningAdapter, "_deploy_showroom")


def test_wait_for_showroom_route_accepts_chart_proxy_route(monkeypatch):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    route_snapshots = iter([
        {"demo": "https://demo.example.test"},
        {
            "demo": "https://demo.example.test",
            "showroom-proxy": "https://showroom.example.test",
        },
    ])
    adapter._get_routes = lambda _namespace: next(route_snapshots)
    monkeypatch.setattr("app.adapters.openshift.provisioning.time.sleep", lambda _seconds: None)

    routes = adapter._wait_for_showroom_route("lab-namespace")

    assert routes["showroom-proxy"] == "https://showroom.example.test"


def test_showroom_namespace_is_labeled_for_namespaced_argocd():
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._core_v1 = MagicMock()

    adapter._create_namespace(
        "lab-showroom", {"argocd.argoproj.io/managed-by": "argocd"}
    )

    body = adapter._core_v1.create_namespace.call_args.kwargs["body"]
    assert body.metadata.labels["argocd.argoproj.io/managed-by"] == "argocd"


def test_guided_lab_namespace_keeps_generated_showroom_host_label_valid():
    namespace = OpenShiftProvisioningAdapter._demo_namespace(
        "smoke-test-tenant",
        "guided-rag-on-xeon",
        "af85a6",
    )

    assert namespace == "launchpad-smoke-test-tenant-guided-rag-on-xeon-af85a6"
    assert len(f"showroom-{namespace}") <= 63


def test_guided_seat_namespace_can_use_stable_seat_suffix():
    seat_id = "003606bd-5b75-40dc-8eb8-8b7533c5de04"
    suffix = seat_id.replace("-", "")[:8]

    namespace = OpenShiftProvisioningAdapter._demo_namespace(
        "smoke-test-tenant", "guided-rag-on-xeon", suffix
    )

    assert namespace.endswith("-003606bd")


def test_gateway_pvc_uses_configured_storage_class():
    manifest = """apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
spec:
  accessModes: [ReadWriteOnce]
"""

    rendered = OpenShiftProvisioningAdapter._inject_storage_class(manifest, "nfs-storage")

    assert "storageClassName: nfs-storage" in rendered
