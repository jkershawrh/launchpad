"""TDD tests for /health/detailed endpoint — Phase 5 gate matrix."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

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


class TestReadinessIsFailClosed:
    def test_mock_mode_is_ready_without_external_dependencies(self):
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with patch.dict("os.environ", {"LAUNCHPAD_MODE": "mock"}, clear=False):
            response = client.get("/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_openshift_mode_rejects_traffic_when_database_is_unavailable(self):
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with (
            patch.dict("os.environ", {"LAUNCHPAD_MODE": "openshift"}, clear=False),
            patch(
                "app.services.health._check_db",
                return_value={"status": "fail", "message": "database unavailable"},
            ),
        ):
            response = client.get("/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["db"]["status"] == "fail"

    def test_standby_control_plane_never_becomes_ready(self):
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with (
            patch.dict(
                "os.environ",
                {
                    "LAUNCHPAD_MODE": "openshift",
                    "LAUNCHPAD_CONTROL_PLANE_ROLE": "standby",
                },
                clear=False,
            ),
            patch(
                "app.services.health._check_db",
                return_value={"status": "pass"},
            ),
        ):
            response = client.get("/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["control_plane_role"] == {
            "status": "fail",
            "role": "standby",
        }

    def test_backend_deployment_uses_fail_closed_readiness(self):
        from pathlib import Path

        import yaml

        root = Path(__file__).resolve().parents[2]
        deployment = list(
            yaml.safe_load_all(
                (root / "deploy/launchpad/base/backend-deployment.yaml").read_text()
            )
        )[0]
        backend = next(
            container
            for container in deployment["spec"]["template"]["spec"]["containers"]
            if container["name"] == "backend"
        )

        assert backend["readinessProbe"]["httpGet"]["path"] == "/ready"

    def test_ha_mode_disables_process_local_lifecycle_loops(self):
        from app.main import _direct_lifecycle_background_tasks_enabled

        with patch.dict(
            "os.environ", {"LIFECYCLE_HA_ENABLED": "true"}, clear=False
        ):
            assert not _direct_lifecycle_background_tasks_enabled()
        with patch.dict(
            "os.environ", {"LIFECYCLE_HA_ENABLED": "false"}, clear=False
        ):
            assert _direct_lifecycle_background_tasks_enabled()


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
    def test_does_not_duplicate_v1_in_configured_api_base(self):
        from app.services.health import _check_litellm

        models = MagicMock()
        models.json.return_value = {"data": [{"id": "granite"}]}
        completion = MagicMock()
        completion.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }
        with (
            patch("app.services.health.httpx.get", return_value=models) as get,
            patch(
                "app.services.health.httpx.post", return_value=completion
            ) as post,
        ):
            result = _check_litellm(
                "http://model-api:8080/v1", "", "granite"
            )

        assert result["status"] == "pass"
        assert get.call_args.args[0] == "http://model-api:8080/v1/models"
        assert post.call_args.args[0] == (
            "http://model-api:8080/v1/chat/completions"
        )

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
