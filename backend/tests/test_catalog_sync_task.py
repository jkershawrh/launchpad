"""TDD tests for catalog sync task — Phase 4 gate matrix."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import yaml

from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem


def _write_catalog_item(base_dir: str, name: str, data: dict) -> str:
    subdir = os.path.join(base_dir, name)
    os.makedirs(subdir, exist_ok=True)
    path = os.path.join(subdir, "catalog-item.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def _minimal_item(catalog_item_id: str, **overrides) -> dict:
    base = {
        "catalog_item_id": catalog_item_id,
        "display_name": f"Test {catalog_item_id}",
        "category": "quick_start",
        "status": "active",
    }
    base.update(overrides)
    return base


# ── Gate 4.1: test_sync_detects_new_item ─────────────────────────────

class TestSyncDetectsNewItem:
    def test_new_yaml_appears_after_sync(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter
        from tasks.catalog_sync import _do_catalog_sync

        _write_catalog_item(str(tmp_path), "original", _minimal_item("original"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert len(adapter.list_items()) == 1

        _write_catalog_item(str(tmp_path), "new-demo", _minimal_item("new-demo"))
        _do_catalog_sync(adapter)
        assert len(adapter.list_items()) == 2
        assert adapter.get_item("new-demo") is not None


# ── Gate 4.2: test_sync_detects_removed_item ─────────────────────────

class TestSyncDetectsRemovedItem:
    def test_deleted_yaml_removed_after_sync(self, tmp_path):
        from app.adapters.file.catalog import FileCatalogAdapter
        from tasks.catalog_sync import _do_catalog_sync

        _write_catalog_item(str(tmp_path), "keep", _minimal_item("keep"))
        path = _write_catalog_item(str(tmp_path), "remove", _minimal_item("remove"))
        adapter = FileCatalogAdapter(str(tmp_path))
        assert len(adapter.list_items()) == 2

        os.remove(path)
        os.rmdir(os.path.dirname(path))
        _do_catalog_sync(adapter)
        assert len(adapter.list_items()) == 1
        assert adapter.get_item("remove") is None


# ── Gate 4.3: test_sync_noop_when_mock ───────────────────────────────

class TestSyncNoopWhenMock:
    def test_mock_adapter_no_crash(self):
        from app.adapters.mock.catalog import MockCatalogAdapter
        from tasks.catalog_sync import _do_catalog_sync

        adapter = MockCatalogAdapter()
        count_before = len(adapter.list_items())
        _do_catalog_sync(adapter)
        assert len(adapter.list_items()) == count_before


# ── Gate 4.7: test_beat_schedule_includes_tasks ──────────────────────

class TestBeatSchedule:
    def test_catalog_sync_in_schedule(self):
        from celery_app import app
        assert "catalog-sync-loop" in app.conf.beat_schedule

    def test_model_health_in_schedule(self):
        from celery_app import app
        assert "model-health-check" in app.conf.beat_schedule
