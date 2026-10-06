from pathlib import Path

import yaml
from app.adapters.file.catalog import FileCatalogAdapter
from app.domain.enums import CatalogCategory, LabRequestStatus
from app.domain.models import LabRequest
from app.services.provisioning import ProvisioningService

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/smoke-test/catalog-item.yaml"


def _catalog() -> dict:
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))


def test_smoke_test_is_an_internal_diagnostic_not_a_learning_experience() -> None:
    item = _catalog()
    metadata = item["metadata"]

    assert item["status"] == "draft"
    assert item["supported_branding"] == ["intel-internal"]
    assert metadata["experience_type"] == "platform_validation"
    assert metadata["audience"] == "platform_operators"
    assert metadata["catalog_visibility"] == "internal_diagnostic"
    assert metadata["participant_orderable"] is False
    assert metadata["learning_contract"] == "not_applicable"
    assert metadata["operator_surfaces"] == []
    assert metadata["inference_claim_status"] == "none"
    assert metadata["hardware_claim_status"] == "none"
    assert "cpu_only" not in metadata
    assert "default_hardware_profile" not in item


def test_smoke_test_provenance_and_lifecycle_are_bound_to_the_launchpad_release() -> None:
    metadata = _catalog()["metadata"]

    assert metadata["provenance"] == {
        "type": "bundled_launchpad_source",
        "release_bound": True,
        "catalog_path": "catalog/smoke-test/catalog-item.yaml",
        "runtime_path": "backend/app/adapters/openshift/provisioning.py",
    }
    assert metadata["certification_status"] == "not_certified_internal_fixture"
    assert metadata["lifecycle_expectations"] == [
        "create",
        "readiness",
        "reclaim",
        "zero_residue",
    ]


def test_draft_smoke_test_rejects_direct_api_ordering() -> None:
    service = ProvisioningService(catalog=FileCatalogAdapter(str(ROOT / "catalog")))
    submitted = service.submit_request(
        LabRequest(
            tenant_id="platform-operators",
            requester_id="diagnostic-runner",
            catalog_item_id="smoke-test",
            requested_mode=CatalogCategory.QUICK_START,
        )
    )

    assert submitted.status == LabRequestStatus.REJECTED
