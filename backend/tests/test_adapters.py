from app.adapters.mock.branding import FileBrandingAdapter
from app.adapters.mock.catalog import MockCatalogAdapter
from app.adapters.mock.constraints import MockConstraintAdapter
from app.adapters.mock.observability import MockObservabilityAdapter
from app.adapters.mock.pool import MockPoolAdapter
from app.adapters.mock.provisioning import MockProvisioningAdapter
from app.adapters.mock.showback import MockShowbackAdapter
from app.adapters.mock.validation import MockValidationAdapter
from app.domain.enums import CatalogCategory, Persistence, SessionStatus
from app.domain.models import LabRequest, LabSession


def test_mock_catalog_adapter_lists_items():
    adapter = MockCatalogAdapter()
    items = adapter.list_items()
    assert len(items) == 18
    ids = {i.catalog_item_id for i in items}
    assert "inference-overdrive-quickstart" in ids
    assert "build-a-rag-app" in ids
    assert "mixed-ai-sandbox" in ids


def test_mock_catalog_adapter_gets_item():
    adapter = MockCatalogAdapter()
    item = adapter.get_item("inference-overdrive-quickstart")
    assert item is not None
    assert item.category == CatalogCategory.QUICK_START


def test_mock_catalog_adapter_validates_active_item():
    adapter = MockCatalogAdapter()
    assert adapter.validate_item("inference-overdrive-quickstart") is True
    assert adapter.validate_item("nonexistent") is False


def test_mock_pool_adapter_reserves_resources():
    adapter = MockPoolAdapter()
    assert adapter.check_capacity("gaudi-endpoint", "standard") is True
    reservation = adapter.reserve("session-1", "gaudi-endpoint", "standard")
    assert reservation["session_id"] == "session-1"
    assert reservation["status"] == "reserved"
    report = adapter.report_allocation()
    assert report["total_reservations"] == 1


def test_mock_pool_adapter_releases_resources():
    adapter = MockPoolAdapter()
    adapter.reserve("session-1", "xeon-basic", "standard")
    assert adapter.release("session-1") is True
    assert adapter.release("nonexistent") is False
    assert adapter.report_allocation()["total_reservations"] == 0


def test_mock_constraint_adapter_allows_valid_request():
    adapter = MockConstraintAdapter()
    request = LabRequest(
        tenant_id="partner-oem-a",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    )
    result = adapter.evaluate(request)
    assert result.allowed is True
    assert result.level == "allowed"


def test_mock_provisioning_adapter_generates_namespace_and_urls():
    adapter = MockProvisioningAdapter()
    request = LabRequest(
        tenant_id="partner-oem-a",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
        hardware_profile="gaudi-endpoint",
        quota_profile="standard",
    )
    catalog = MockCatalogAdapter().get_item("inference-overdrive-quickstart")
    plan = adapter.create_plan(request, catalog)
    assert plan.target_namespace.startswith("lab-partner-oem-a-")
    assert len(plan.steps) == 4

    result = adapter.provision(plan)
    assert result.namespace == plan.target_namespace
    assert "lab.example.com" in result.lab_url
    assert "dashboard.example.com" in result.dashboard_url


def test_mock_validation_adapter_returns_pass_results():
    adapter = MockValidationAdapter()
    session = LabSession(
        request_id="r1",
        tenant_id="t1",
        catalog_item_id="c1",
        namespace="lab-test-001",
        lab_url="https://lab.example.com/test",
        dashboard_url="https://dashboard.example.com/test",
    )
    results = adapter.validate(session)
    assert len(results) == 3
    assert all(r.result.value == "pass" for r in results)


def test_mock_observability_adapter_generates_dashboard_url():
    adapter = MockObservabilityAdapter()
    session = LabSession(
        request_id="r1",
        tenant_id="t1",
        catalog_item_id="c1",
        namespace="lab-test-001",
    )
    url = adapter.create_dashboard(session)
    assert "dashboard.example.com" in url
    assert "lab-test-001" in url


def test_mock_observability_adapter_returns_metrics():
    adapter = MockObservabilityAdapter()
    metrics = adapter.get_metrics("s1")
    assert "cpu_usage_percent" in metrics
    assert adapter.get_health("s1") == "healthy"


def test_mock_showback_adapter_generates_record():
    adapter = MockShowbackAdapter()
    session = LabSession(
        request_id="r1",
        tenant_id="partner-oem-a",
        catalog_item_id="inference-overdrive-quickstart",
        namespace="lab-test-001",
    )
    record = adapter.create_record(session)
    assert record.tenant_id == "partner-oem-a"
    assert record.duration_seconds == 14400
    assert record.model_requests == 150


def test_mock_showback_adapter_summarizes():
    adapter = MockShowbackAdapter()
    session = LabSession(
        request_id="r1",
        tenant_id="t1",
        catalog_item_id="c1",
        namespace="ns1",
    )
    adapter.create_record(session)
    summary = adapter.summarize("t1")
    assert summary["total_sessions"] == 1


def test_file_branding_adapter_loads_profile():
    adapter = FileBrandingAdapter()
    profile = adapter.load_profile("redhat-intel-default")
    assert profile is not None
    assert profile.title == "Partner AI Launchpad"
    assert profile.primary_color == "#EE0000"


def test_file_branding_adapter_lists_profiles():
    adapter = FileBrandingAdapter()
    profiles = adapter.list_profiles()
    assert len(profiles) == 3
