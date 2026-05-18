import pytest
from pydantic import ValidationError

from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem


def test_catalog_item_accepts_quick_start(quickstart_catalog_item):
    assert quickstart_catalog_item.category == CatalogCategory.QUICK_START
    assert quickstart_catalog_item.status == CatalogStatus.ACTIVE
    assert quickstart_catalog_item.catalog_item_id == "inference-overdrive-quickstart"


def test_catalog_item_accepts_guided_build(guided_build_catalog_item):
    assert guided_build_catalog_item.category == CatalogCategory.GUIDED_BUILD
    assert guided_build_catalog_item.catalog_item_id == "build-a-rag-app"


def test_catalog_item_accepts_open_sandbox(sandbox_catalog_item):
    assert sandbox_catalog_item.category == CatalogCategory.OPEN_SANDBOX
    assert sandbox_catalog_item.catalog_item_id == "mixed-ai-sandbox"


def test_catalog_item_rejects_empty_id():
    with pytest.raises(ValidationError):
        CatalogItem(
            catalog_item_id="",
            display_name="Bad Item",
            category=CatalogCategory.QUICK_START,
        )


def test_catalog_item_defaults():
    item = CatalogItem(
        catalog_item_id="test-item",
        display_name="Test",
        category=CatalogCategory.QUICK_START,
    )
    assert item.version == "1.0.0"
    assert item.status == CatalogStatus.DRAFT
    assert item.required_capabilities == []
    assert item.metadata == {}
