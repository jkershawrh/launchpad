import pytest

from app.domain.enums import (
    CatalogCategory,
    CatalogStatus,
    Persistence,
    TenantType,
    ValidationResultStatus,
)
from app.domain.models import (
    CatalogItem,
    LabRequest,
    LabSession,
    Tenant,
    ValidationResult,
)


@pytest.fixture
def valid_tenant():
    return Tenant(
        tenant_id="partner-oem-a",
        display_name="Partner OEM A",
        tenant_type=TenantType.PARTNER,
        branding_profile_id="partner-oem-a",
        default_quota_profile="standard",
        default_ttl="8h",
        cost_center="demo-partner-oem-a",
    )


@pytest.fixture
def quickstart_catalog_item():
    return CatalogItem(
        catalog_item_id="inference-overdrive-quickstart",
        display_name="Inference Overdrive Quick Start",
        description="Fast-start inference demo",
        category=CatalogCategory.QUICK_START,
        status=CatalogStatus.ACTIVE,
        default_hardware_profile="gaudi-endpoint",
        default_quota_profile="standard",
        default_ttl="4h",
    )


@pytest.fixture
def guided_build_catalog_item():
    return CatalogItem(
        catalog_item_id="build-a-rag-app",
        display_name="Build a RAG App",
        description="Guided RAG application build",
        category=CatalogCategory.GUIDED_BUILD,
        status=CatalogStatus.ACTIVE,
    )


@pytest.fixture
def sandbox_catalog_item():
    return CatalogItem(
        catalog_item_id="mixed-ai-sandbox",
        display_name="Mixed AI Sandbox",
        description="Open sandbox for AI experimentation",
        category=CatalogCategory.OPEN_SANDBOX,
        status=CatalogStatus.ACTIVE,
    )


@pytest.fixture
def ephemeral_lab_request():
    return LabRequest(
        tenant_id="partner-oem-a",
        requester_id="demo-engineer-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
        persistence=Persistence.EPHEMERAL,
        ttl="4h",
    )


@pytest.fixture
def persistent_lab_request():
    return LabRequest(
        tenant_id="redhat-internal",
        requester_id="sa-engineer-1",
        catalog_item_id="build-a-rag-app",
        requested_mode=CatalogCategory.GUIDED_BUILD,
        persistence=Persistence.PERSISTENT,
        ttl="8h",
    )


@pytest.fixture
def lab_session():
    return LabSession(
        request_id="req-001",
        tenant_id="partner-oem-a",
        catalog_item_id="inference-overdrive-quickstart",
        namespace="lab-partner-oem-a-001",
    )


@pytest.fixture
def passing_validation():
    return ValidationResult(
        session_id="session-001",
        check_name="smoke-test",
        result=ValidationResultStatus.PASS,
        message="All endpoints responding",
    )


@pytest.fixture
def failing_validation():
    return ValidationResult(
        session_id="session-001",
        check_name="smoke-test",
        result=ValidationResultStatus.FAIL,
        message="Model endpoint unreachable",
    )
