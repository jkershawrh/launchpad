from app.domain.enums import CatalogCategory, LabRequestStatus, Persistence, SessionStatus
from app.domain.models import LabRequest
from app.services.provisioning import ProvisioningService


def _run_full_lifecycle(service: ProvisioningService, request: LabRequest):
    submitted = service.submit_request(request)
    assert submitted.status == LabRequestStatus.ACCEPTED

    session = service.provision(submitted.request_id)
    assert session.status == SessionStatus.VALIDATING
    assert session.namespace is not None
    assert session.lab_url is not None

    session = service.validate_session(session.session_id)
    assert session.status == SessionStatus.READY
    assert len(session.validation_results) == 3

    handoff = service.get_handoff(session.session_id)
    assert "Your AI Lab is Ready" in handoff.to_markdown()
    assert handoff.lab_url is not None

    showback = service.get_showback(session.session_id)
    assert showback.tenant_id == request.tenant_id
    assert showback.duration_seconds > 0

    report = service.get_repeatability_report(session.session_id)
    assert report.repeatability_score == 100

    security = service.get_security_plan(session.session_id)
    assert "Namespace" in security.planned_artifacts()
    assert "ResourceQuota" in security.planned_artifacts()

    return session


def test_e2e_quick_start_lab_request_to_ready():
    service = ProvisioningService()
    request = LabRequest(
        tenant_id="partner-oem-a",
        requester_id="demo-engineer-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
        persistence=Persistence.EPHEMERAL,
        ttl="4h",
        hardware_profile="gaudi-endpoint",
        quota_profile="standard",
        branding_profile_id="partner-oem-a",
    )
    session = _run_full_lifecycle(service, request)
    assert session.catalog_item_id == "inference-overdrive-quickstart"


def test_e2e_guided_build_lab_request_to_ready():
    service = ProvisioningService()
    request = LabRequest(
        tenant_id="redhat-internal",
        requester_id="sa-engineer-1",
        catalog_item_id="build-a-rag-app",
        requested_mode=CatalogCategory.GUIDED_BUILD,
        persistence=Persistence.PERSISTENT,
        ttl="8h",
        hardware_profile="xeon-basic",
        quota_profile="standard",
        branding_profile_id="redhat-intel-default",
    )
    session = _run_full_lifecycle(service, request)
    assert session.catalog_item_id == "build-a-rag-app"


def test_e2e_open_sandbox_request_to_ready():
    service = ProvisioningService()
    request = LabRequest(
        tenant_id="intel-internal",
        requester_id="ai-researcher-1",
        catalog_item_id="mixed-ai-sandbox",
        requested_mode=CatalogCategory.OPEN_SANDBOX,
        persistence=Persistence.PERSISTENT,
        ttl="12h",
        hardware_profile="mixed-overdrive",
        quota_profile="large",
        branding_profile_id="redhat-intel-default",
    )
    session = _run_full_lifecycle(service, request)
    assert session.catalog_item_id == "mixed-ai-sandbox"


def test_e2e_rejects_unknown_catalog_item():
    service = ProvisioningService()
    request = LabRequest(
        tenant_id="partner-oem-a",
        requester_id="user-1",
        catalog_item_id="nonexistent-item",
        requested_mode=CatalogCategory.QUICK_START,
    )
    submitted = service.submit_request(request)
    assert submitted.status == LabRequestStatus.REJECTED


def test_e2e_full_lifecycle_to_reclaimed():
    service = ProvisioningService()
    request = LabRequest(
        tenant_id="partner-oem-a",
        requester_id="demo-engineer-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
        persistence=Persistence.EPHEMERAL,
        ttl="4h",
    )
    session = _run_full_lifecycle(service, request)

    session = service.activate_session(session.session_id)
    assert session.status == SessionStatus.ACTIVE
    assert session.started_at is not None

    session = service.reset_session(session.session_id)
    assert session.status == SessionStatus.RESETTING

    session = service.reclaim_session(session.session_id)
    assert session.status == SessionStatus.RECLAIMED
    assert session.completed_at is not None
    assert len(session.lifecycle_events) == 6
