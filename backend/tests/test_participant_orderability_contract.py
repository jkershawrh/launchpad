from pathlib import Path

import pytest
from app.adapters.file.catalog import FileCatalogAdapter
from app.domain.models import Workshop
from app.services.provisioning import ProvisioningService

ROOT = Path(__file__).resolve().parents[2]


def _service() -> ProvisioningService:
    return ProvisioningService(catalog=FileCatalogAdapter(str(ROOT / "catalog")))


def test_draft_catalog_item_cannot_be_ordered_through_workshop_api() -> None:
    service = _service()
    workshop = Workshop(
        tenant_id="participant-tenant",
        catalog_item_id="smoke-test",
        num_users=1,
    )

    preview = service.preview_workshop_capacity(workshop)
    assert preview["can_provision"] is False
    assert "not active" in preview["reason"]
    with pytest.raises(ValueError, match="not active"):
        service.create_workshop_order(workshop)


def test_active_compatibility_alias_remains_available_to_legacy_direct_clients() -> None:
    service = _service()
    workshop = Workshop(
        tenant_id="legacy-client",
        catalog_item_id="cpu-inference-serving",
        num_users=1,
    )

    assert service._validate_workshop_seat_limit(workshop) == 5
