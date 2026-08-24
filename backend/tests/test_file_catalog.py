"""TDD tests for FileCatalogAdapter — Phase 1 gate matrix."""
from __future__ import annotations

import os
import tempfile
import textwrap

import pytest
import yaml

from app.adapters.interfaces import CatalogAdapter
from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem


def _write_catalog_item(base_dir: str, name: str, data: dict) -> str:
    """Write a catalog-item.yaml into a named subdirectory."""
    subdir = os.path.join(base_dir, name)
    os.makedirs(subdir, exist_ok=True)
    path = os.path.join(subdir, "catalog-item.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def _minimal_item(catalog_item_id: str, **overrides) -> dict:
    """Return the minimal valid catalog item dict."""
    base = {
        "catalog_item_id": catalog_item_id,
        "display_name": f"Test {catalog_item_id}",
        "category": "quick_start",
        "status": "active",
    }
    base.update(overrides)
    return base


# ── Gate 1.1: test_loads_yaml_directory ──────────────────────────────

class TestLoadsYamlDirectory:
    def test_reads_all_subdirectories(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "demo-a", _minimal_item("demo-a"))
        _write_catalog_item(str(tmp_path), "demo-b", _minimal_item("demo-b"))
        _write_catalog_item(str(tmp_path), "demo-c", _minimal_item("demo-c"))

        adapter = FileCatalogAdapter(str(tmp_path))
        items = adapter.list_items()
        assert len(items) == 3
        ids = {item.catalog_item_id for item in items}
        assert ids == {"demo-a", "demo-b", "demo-c"}

    def test_returns_catalog_item_instances(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "demo-x", _minimal_item("demo-x"))
        adapter = FileCatalogAdapter(str(tmp_path))
        items = adapter.list_items()
        assert all(isinstance(item, CatalogItem) for item in items)

    def test_preserves_all_fields(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        data = _minimal_item(
            "full-item",
            description="A full item",
            version="2.0.0",
            required_capabilities=["openshift", "model_endpoint"],
            default_hardware_profile="xeon-basic",
            default_quota_profile="standard",
            default_ttl="4h",
            metadata={"deploy_method": "helm", "required_models": ["granite-2b-cpu"]},
        )
        _write_catalog_item(str(tmp_path), "full-item", data)
        adapter = FileCatalogAdapter(str(tmp_path))
        item = adapter.list_items()[0]
        assert item.description == "A full item"
        assert item.version == "2.0.0"
        assert item.required_capabilities == ["openshift", "model_endpoint"]
        assert item.default_hardware_profile == "xeon-basic"
        assert item.metadata["deploy_method"] == "helm"
        assert item.metadata["required_models"] == ["granite-2b-cpu"]


# ── Gate 1.2: test_get_item_by_id ────────────────────────────────────

class TestGetItemById:
    def test_returns_correct_item(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "target", _minimal_item("target", display_name="Target Demo"))
        _write_catalog_item(str(tmp_path), "other", _minimal_item("other"))
        adapter = FileCatalogAdapter(str(tmp_path))

        item = adapter.get_item("target")
        assert item is not None
        assert item.catalog_item_id == "target"
        assert item.display_name == "Target Demo"

    def test_returns_none_for_missing(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "exists", _minimal_item("exists"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.get_item("does-not-exist") is None


# ── Gate 1.3: test_validate_item ─────────────────────────────────────

class TestValidateItem:
    def test_active_item_validates(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "active-demo", _minimal_item("active-demo", status="active"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.validate_item("active-demo") is True

    def test_draft_item_does_not_validate(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "draft-demo", _minimal_item("draft-demo", status="draft"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.validate_item("draft-demo") is False

    def test_deprecated_item_does_not_validate(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "old-demo", _minimal_item("old-demo", status="deprecated"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.validate_item("old-demo") is False

    def test_missing_item_does_not_validate(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.validate_item("ghost") is False


# ── Gate 1.4: test_rejects_malformed_yaml ────────────────────────────

class TestRejectsMalformedYaml:
    def test_skips_invalid_yaml_syntax(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "good", _minimal_item("good"))
        bad_dir = os.path.join(str(tmp_path), "bad")
        os.makedirs(bad_dir)
        with open(os.path.join(bad_dir, "catalog-item.yaml"), "w") as f:
            f.write("{{not valid yaml::")

        adapter = FileCatalogAdapter(str(tmp_path))
        items = adapter.list_items()
        assert len(items) == 1
        assert items[0].catalog_item_id == "good"

    def test_skips_missing_required_fields(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "good", _minimal_item("good"))
        _write_catalog_item(str(tmp_path), "incomplete", {"display_name": "No ID or category"})

        adapter = FileCatalogAdapter(str(tmp_path))
        items = adapter.list_items()
        assert len(items) == 1
        assert items[0].catalog_item_id == "good"

    def test_skips_dirs_without_catalog_yaml(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "good", _minimal_item("good"))
        os.makedirs(os.path.join(str(tmp_path), "empty-dir"))

        adapter = FileCatalogAdapter(str(tmp_path))
        assert len(adapter.list_items()) == 1


# ── Gate 1.5: test_empty_directory ───────────────────────────────────

class TestEmptyDirectory:
    def test_returns_empty_list(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.list_items() == []

    def test_get_item_returns_none(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.get_item("anything") is None


# ── Gate 1.6: test_reload_picks_up_changes ───────────────────────────

class TestReload:
    def test_detects_new_item(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "original", _minimal_item("original"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert len(adapter.list_items()) == 1

        _write_catalog_item(str(tmp_path), "new-demo", _minimal_item("new-demo"))
        adapter.reload()
        assert len(adapter.list_items()) == 2
        assert adapter.get_item("new-demo") is not None

    def test_detects_deleted_item(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "keep", _minimal_item("keep"))
        path = _write_catalog_item(str(tmp_path), "remove", _minimal_item("remove"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert len(adapter.list_items()) == 2

        os.remove(path)
        os.rmdir(os.path.dirname(path))
        adapter.reload()
        assert len(adapter.list_items()) == 1
        assert adapter.get_item("remove") is None

    def test_detects_updated_item(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "evolving", _minimal_item("evolving", display_name="V1"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert adapter.get_item("evolving").display_name == "V1"

        _write_catalog_item(str(tmp_path), "evolving", _minimal_item("evolving", display_name="V2"))
        adapter.reload()
        assert adapter.get_item("evolving").display_name == "V2"


# ── Gate 1.C1: CatalogAdapter protocol ──────────────────────────────

class TestCatalogAdapterProtocol:
    def test_has_list_items(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        adapter = FileCatalogAdapter(str(tmp_path))
        assert hasattr(adapter, "list_items")
        assert callable(adapter.list_items)

    def test_has_get_item(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        adapter = FileCatalogAdapter(str(tmp_path))
        assert hasattr(adapter, "get_item")
        assert callable(adapter.get_item)

    def test_has_validate_item(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter

        adapter = FileCatalogAdapter(str(tmp_path))
        assert hasattr(adapter, "validate_item")
        assert callable(adapter.validate_item)


# ── Gate 1.T1: Contract test — File vs Mock identical shape ──────────

class TestContractFileVsMock:
    def test_list_items_returns_same_type(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter
        from app.adapters.mock.catalog import MockCatalogAdapter

        _write_catalog_item(str(tmp_path), "test", _minimal_item("test"))
        file_adapter = FileCatalogAdapter(str(tmp_path))
        mock_adapter = MockCatalogAdapter()

        file_items = file_adapter.list_items()
        mock_items = mock_adapter.list_items()

        assert type(file_items) is type(mock_items)
        assert type(file_items[0]) is type(mock_items[0])

    def test_get_item_returns_same_type(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter
        from app.adapters.mock.catalog import MockCatalogAdapter

        _write_catalog_item(str(tmp_path), "test", _minimal_item("test"))
        file_adapter = FileCatalogAdapter(str(tmp_path))
        mock_adapter = MockCatalogAdapter()

        file_item = file_adapter.get_item("test")
        mock_item = mock_adapter.get_item("inference-overdrive-quickstart")

        assert type(file_item) is type(mock_item)

    def test_get_missing_returns_none_for_both(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter
        from app.adapters.mock.catalog import MockCatalogAdapter

        file_adapter = FileCatalogAdapter(str(tmp_path))
        mock_adapter = MockCatalogAdapter()

        assert file_adapter.get_item("nope") is None
        assert mock_adapter.get_item("nope") is None


# ── Gate 1.B1: BDD — 3 subdirs → 3 items ────────────────────────────

class TestBDD:
    def test_three_subdirs_three_items(self, tmp_path):
        """Given 3 demo subdirs, When constructed, Then list_items returns 3."""
        from app.adapters.file.catalog import FileCatalogAdapter

        for name in ["alpha", "beta", "gamma"]:
            _write_catalog_item(str(tmp_path), name, _minimal_item(name))

        adapter = FileCatalogAdapter(str(tmp_path))
        assert len(adapter.list_items()) == 3

    def test_new_dir_plus_reload_appears(self, tmp_path):
        """Given running adapter, When new dir added + reload(), Then new demo in list."""
        from app.adapters.file.catalog import FileCatalogAdapter

        _write_catalog_item(str(tmp_path), "initial", _minimal_item("initial"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert len(adapter.list_items()) == 1

        _write_catalog_item(str(tmp_path), "added", _minimal_item("added"))
        adapter.reload()
        items = adapter.list_items()
        assert len(items) == 2
        assert any(i.catalog_item_id == "added" for i in items)
