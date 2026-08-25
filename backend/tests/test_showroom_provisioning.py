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


def test_showroom_html_contains_safe_steps_and_workspace_link():
    document = OpenShiftProvisioningAdapter._showroom_html(
        "RAG <Lab>",
        [{"title": "Test retrieval", "description": "Run <script>alert(1)</script>"}],
        "https://workspace.example.test",
    )

    assert "RAG &lt;Lab&gt;" in document
    assert "Test retrieval" in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document
    assert 'href="https://workspace.example.test"' in document


def test_showroom_hostname_stays_short_for_long_lab_namespaces():
    hostname = OpenShiftProvisioningAdapter._showroom_hostname(
        "launchpad-demo-smoke-test-tenant-guided-rag-on-xeon-af85a6",
        "apps.oberon.example.com",
    )

    assert hostname == "showroom-af85a6.apps.oberon.example.com"
    assert len(hostname.split(".", 1)[0]) <= 63
