"""TDD tests for model health task — Phase 4 gate matrix."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem


def _make_item(item_id, required_models=None, status="active"):
    data = {
        "catalog_item_id": item_id,
        "display_name": f"Test {item_id}",
        "category": CatalogCategory.QUICK_START,
        "status": CatalogStatus(status),
    }
    if required_models is not None:
        data["metadata"] = {"required_models": required_models}
    return CatalogItem(**data)


# ── Gate 4.4: test_health_marks_unavailable ──────────────────────────

class TestHealthMarksUnavailable:
    def test_unhealthy_model_sets_draft(self):
        from tasks.model_health import _do_model_health_check

        item = _make_item("demo-a", required_models=["granite-2b-cpu"])
        adapter = MagicMock()
        adapter.list_items.return_value = [item]

        with patch("tasks.model_health.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"data": []}  # no models available
            mock_httpx.get.return_value = mock_resp

            _do_model_health_check(adapter, "http://fake:4000")

        adapter.set_status.assert_called_once_with("demo-a", CatalogStatus.DRAFT)


# ── Gate 4.5: test_health_restores_available ─────────────────────────

class TestHealthRestoresAvailable:
    def test_healthy_model_restores_active(self):
        from tasks.model_health import _do_model_health_check

        item = _make_item("demo-a", required_models=["granite-2b-cpu"], status="draft")
        adapter = MagicMock()
        adapter.list_items.return_value = [item]

        with patch("tasks.model_health.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"data": [{"id": "granite-2b-cpu"}]}
            mock_httpx.get.return_value = mock_resp

            _do_model_health_check(adapter, "http://fake:4000")

        adapter.set_status.assert_called_once_with("demo-a", CatalogStatus.ACTIVE)


# ── Gate 4.6: test_health_skips_no_model_items ───────────────────────

class TestHealthSkipsNoModelItems:
    def test_no_required_models_untouched(self):
        from tasks.model_health import _do_model_health_check

        item = _make_item("no-models")
        adapter = MagicMock()
        adapter.list_items.return_value = [item]

        with patch("tasks.model_health.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"data": []}
            mock_httpx.get.return_value = mock_resp

            _do_model_health_check(adapter, "http://fake:4000")

        adapter.set_status.assert_not_called()

    def test_already_active_stays_active(self):
        from tasks.model_health import _do_model_health_check

        item = _make_item("demo-a", required_models=["granite-2b-cpu"], status="active")
        adapter = MagicMock()
        adapter.list_items.return_value = [item]

        with patch("tasks.model_health.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"data": [{"id": "granite-2b-cpu"}]}
            mock_httpx.get.return_value = mock_resp

            _do_model_health_check(adapter, "http://fake:4000")

        adapter.set_status.assert_not_called()
