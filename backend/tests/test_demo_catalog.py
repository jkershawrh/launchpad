"""
Phase B — Demo Catalog TDD Red/Green Matrix

Verifies all 11 demo items are properly defined as catalog items.
"""
import os

import pytest
from pydantic import ValidationError

from app.adapters.mock.catalog import MockCatalogAdapter
from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem

DEMO_QUICKSTARTS = [
    "inference-overdrive",
    "enterprise-rag",
    "aiops-copilot",
    "recovery-demo",
    "replay-comparison",
]

DEMO_GUIDED_BUILDS = [
    "governed-agent",
    "agent-swarm",
    "research-agent",
    "workload-generator",
    "training-demo",
]

DEMO_SANDBOXES = [
    "full-platform-sandbox",
]

ALL_DEMO_IDS = DEMO_QUICKSTARTS + DEMO_GUIDED_BUILDS + DEMO_SANDBOXES
ORIGINAL_IDS = ["inference-overdrive-quickstart", "build-a-rag-app", "mixed-ai-sandbox"]


@pytest.fixture
def catalog():
    return MockCatalogAdapter()


# ─── B1: Catalog has 14 total items (3 original + 11 demos) ──────────────────

def test_catalog_lists_all_items_including_demos(catalog):
    items = catalog.list_items()
    assert len(items) == 25
    ids = {i.catalog_item_id for i in items}
    for demo_id in ALL_DEMO_IDS:
        assert demo_id in ids, f"Missing demo item: {demo_id}"


def test_catalog_rejects_invalid_demo_item(catalog):
    assert catalog.get_item("nonexistent-demo-xyz") is None
    assert catalog.validate_item("nonexistent-demo-xyz") is False


# ─── B2: Each demo has hardware profile ──────────────────────────────────────

def test_demo_items_have_hardware_profiles(catalog):
    for demo_id in ALL_DEMO_IDS:
        item = catalog.get_item(demo_id)
        assert item is not None, f"Missing: {demo_id}"
        assert item.default_hardware_profile is not None, f"{demo_id} missing hardware profile"


def test_demo_item_missing_hardware_rejected():
    with pytest.raises(ValidationError):
        CatalogItem(
            catalog_item_id="",
            display_name="Bad",
            category=CatalogCategory.QUICK_START,
        )


# ─── B3: Each demo has validation refs ───────────────────────────────────────

def test_demo_items_have_validation_refs(catalog):
    for demo_id in ALL_DEMO_IDS:
        item = catalog.get_item(demo_id)
        assert len(item.validation_refs) > 0, f"{demo_id} missing validation refs"


def test_demo_item_missing_validation_is_empty_list():
    item = CatalogItem(
        catalog_item_id="no-validation",
        display_name="No Validation",
        category=CatalogCategory.QUICK_START,
    )
    assert item.validation_refs == []


# ─── B4: Each demo has handoff template ──────────────────────────────────────

def test_demo_items_have_handoff_templates(catalog):
    for demo_id in ALL_DEMO_IDS:
        item = catalog.get_item(demo_id)
        assert item.handoff_template is not None, f"{demo_id} missing handoff template"


def test_demo_item_missing_handoff_is_none():
    item = CatalogItem(
        catalog_item_id="no-handoff",
        display_name="No Handoff",
        category=CatalogCategory.QUICK_START,
    )
    assert item.handoff_template is None


# ─── B5: Quick starts correct category ───────────────────────────────────────

def test_quickstart_demos_correct_category(catalog):
    for demo_id in DEMO_QUICKSTARTS:
        item = catalog.get_item(demo_id)
        assert item.category == CatalogCategory.QUICK_START, f"{demo_id} should be quick_start"


def test_rejects_wrong_category_for_quickstart(catalog):
    for demo_id in DEMO_GUIDED_BUILDS:
        item = catalog.get_item(demo_id)
        assert item.category != CatalogCategory.QUICK_START, f"{demo_id} should not be quick_start"


# ─── B6: Guided builds correct category ──────────────────────────────────────

def test_guided_demos_correct_category(catalog):
    for demo_id in DEMO_GUIDED_BUILDS:
        item = catalog.get_item(demo_id)
        assert item.category == CatalogCategory.GUIDED_BUILD, f"{demo_id} should be guided_build"


# ─── B7: Sandbox correct category ────────────────────────────────────────────

def test_sandbox_demo_correct_category(catalog):
    for demo_id in DEMO_SANDBOXES:
        item = catalog.get_item(demo_id)
        assert item.category == CatalogCategory.OPEN_SANDBOX, f"{demo_id} should be open_sandbox"


# ─── B8: API serves demo items ───────────────────────────────────────────────

def test_api_lists_demo_catalog_items():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/catalog")
    assert resp.status_code == 200
    items = resp.json()
    ids = {i["catalog_item_id"] for i in items}
    for demo_id in ALL_DEMO_IDS:
        assert demo_id in ids, f"API missing: {demo_id}"


def test_api_404_for_unknown_demo():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/catalog/nonexistent-demo-xyz")
    assert resp.status_code == 404


# ─── B9: Demo metadata has source path ───────────────────────────────────────

def test_demo_items_have_source_metadata(catalog):
    for demo_id in ALL_DEMO_IDS:
        item = catalog.get_item(demo_id)
        assert "demo_source" in item.metadata, f"{demo_id} missing demo_source metadata"


def test_demo_item_source_path_exists(catalog):
    demos_root = os.path.join(os.path.dirname(__file__), "..", "..", "demos")
    for demo_id in ALL_DEMO_IDS:
        item = catalog.get_item(demo_id)
        source = item.metadata["demo_source"]
        if source == "all":
            continue
        if source.startswith("overdrive/"):
            module_name = source.split("/")[1]
            full_path = os.path.join(demos_root, "gateway", "overdrive", f"{module_name}.py")
        elif source == "gateway":
            full_path = os.path.join(demos_root, "gateway")
        else:
            full_path = os.path.join(demos_root, source)
        assert os.path.exists(full_path), f"{demo_id}: source path {full_path} does not exist"


# ─── B10: Original 3 items unchanged ─────────────────────────────────────────

def test_original_catalog_items_unchanged(catalog):
    for orig_id in ORIGINAL_IDS:
        item = catalog.get_item(orig_id)
        assert item is not None, f"Original item {orig_id} missing"
        assert item.status == CatalogStatus.ACTIVE
