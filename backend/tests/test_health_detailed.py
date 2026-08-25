"""TDD tests for /health/detailed endpoint — Phase 5 gate matrix."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Gate 5.1: test_shallow_health_unchanged ──────────────────────────

class TestShallowHealthUnchanged:
    def test_returns_ok(self):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "launchpad"


# ── Gate 5.2: test_detailed_returns_checks ───────────────────────────

class TestDetailedReturnsChecks:
    def test_has_required_keys(self):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "checks" in data
        assert "timestamp" in data
        assert "uptime_seconds" in data

    def test_status_is_valid_value(self):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/detailed")
        data = resp.json()
        assert data["status"] in ("ok", "degraded", "unhealthy")


# ── Gate 5.5: test_ok_in_mock_mode ───────────────────────────────────

class TestOkInMockMode:
    def test_mock_mode_returns_ok(self):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch.dict("os.environ", {"LAUNCHPAD_MODE": "mock"}, clear=False):
            resp = client.get("/health/detailed")
            data = resp.json()
            assert data["status"] == "ok"


class TestLiteLLMHealth:
    def test_requires_authenticated_models(self):
        from app.services.health import _check_litellm

        response = MagicMock()
        response.json.return_value = {"data": [{"id": "granite"}]}
        with patch("app.services.health.httpx.get", return_value=response) as get:
            result = _check_litellm("http://litellm:4000", "master")

        assert result == {"status": "pass", "models_available": 1}
        assert get.call_args.kwargs["headers"] == {
            "Authorization": "Bearer master"
        }
        response.raise_for_status.assert_called_once()

    def test_optional_inference_canary_must_return_a_choice(self):
        from app.services.health import _check_litellm

        models = MagicMock()
        models.json.return_value = {"data": [{"id": "granite"}]}
        completion = MagicMock()
        completion.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        with (
            patch("app.services.health.httpx.get", return_value=models),
            patch("app.services.health.httpx.post", return_value=completion) as post,
        ):
            result = _check_litellm(
                "http://litellm:4000", "master", "granite"
            )

        assert result["inference_canary"] == "pass"
        assert post.call_args.kwargs["json"]["max_tokens"] == 3

    def test_empty_model_list_is_degraded(self):
        from app.services.health import _check_litellm

        response = MagicMock()
        response.json.return_value = {"data": []}
        with patch("app.services.health.httpx.get", return_value=response):
            result = _check_litellm("http://litellm:4000", "master")

        assert result["status"] == "fail"
