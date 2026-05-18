#!/usr/bin/env python3
"""
Tests for API Endpoints (Stage 9)

Two tiers:
- Structural: validates module exists, endpoints defined, correct patterns
- Behavioral: uses FastAPI TestClient to make real HTTP calls (no DB required —
  endpoints return 503 when DB is down, which is correct and testable)
"""

import os
import sys
import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def gateway_dir(project_root) -> Path:
    return project_root / "gateway"


@pytest.fixture
def test_client(gateway_dir):
    """Create a FastAPI TestClient with lifespan initialized"""
    sys.path.insert(0, str(gateway_dir))
    try:
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    except ImportError:
        pytest.skip("FastAPI or gateway dependencies not installed")
    finally:
        if str(gateway_dir) in sys.path:
            sys.path.remove(str(gateway_dir))


# --- Structural Tests ---

class TestAPIModule:
    """Test api.py module structure"""

    def test_api_module_exists(self, gateway_dir):
        assert (gateway_dir / "api.py").exists()

    def test_api_module_compiles(self, gateway_dir):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(gateway_dir / "api.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_api_has_router(self, gateway_dir):
        content = (gateway_dir / "api.py").read_text()
        assert 'APIRouter' in content
        assert 'api_router' in content

    def test_api_uses_db_functions_not_pool(self, gateway_dir):
        """API should call db module functions, not access db._pool directly"""
        content = (gateway_dir / "api.py").read_text()
        assert 'db._pool' not in content, \
            "Should use db.get_*() functions, not db._pool directly"

    def test_api_has_consistent_error_handling(self, gateway_dir):
        """All endpoints should use _require_db() for consistency"""
        content = (gateway_dir / "api.py").read_text()
        assert '_require_db' in content, "Should have _require_db helper"
        endpoint_count = content.count('@api_router.')
        require_count = content.count('await _require_db()')
        assert require_count >= endpoint_count - 1, \
            f"Only {require_count} _require_db() calls for {endpoint_count} endpoints"


class TestEndpointDefinitions:
    """Test that all required endpoints are defined"""

    def test_has_list_requests(self, gateway_dir):
        content = (gateway_dir / "api.py").read_text()
        assert '/requests"' in content or "'/requests'" in content

    def test_has_get_request_by_id(self, gateway_dir):
        content = (gateway_dir / "api.py").read_text()
        assert 'request_id' in content
        assert 'get_request_by_id' in content, \
            "Should use db.get_request_by_id() for single lookups"

    def test_has_list_decisions(self, gateway_dir):
        content = (gateway_dir / "api.py").read_text()
        assert '/decisions"' in content or "'/decisions'" in content

    def test_has_get_decision_by_id(self, gateway_dir):
        content = (gateway_dir / "api.py").read_text()
        assert 'get_decision_by_id' in content, \
            "Should use db.get_decision_by_id() for single lookups"

    def test_has_approve_endpoint(self, gateway_dir):
        content = (gateway_dir / "api.py").read_text()
        assert 'approve' in content
        assert 'approved_by' in content

    def test_has_analytics_endpoints(self, gateway_dir):
        content = (gateway_dir / "api.py").read_text()
        assert 'routing-distribution' in content or 'routing_distribution' in content
        assert 'latency-percentiles' in content or 'latency_percentiles' in content
        assert 'cost-by-task' in content or 'cost_by_task' in content
        assert 'governance-summary' in content or 'governance_summary' in content

    def test_approve_validates_approved_by(self, gateway_dir):
        """approve endpoint should require approved_by parameter"""
        content = (gateway_dir / "api.py").read_text()
        assert 'min_length' in content, \
            "approved_by should be validated (required, non-empty)"


# --- Behavioral Tests (FastAPI TestClient) ---

class TestGatewayHealth:
    """Test gateway health endpoint works"""

    def test_health_returns_200(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "backends" in data
        assert "routes" in data

    def test_health_reports_version(self, test_client):
        response = test_client.get("/health")
        data = response.json()
        assert "version" in data


@pytest.mark.skipif(
    bool(os.environ.get("DATABASE_URL")),
    reason="DATABASE_URL is set — these tests verify behavior when DB is unavailable"
)
class TestAPIWithoutDB:
    """Test that API endpoints return 503 when DB is not connected"""

    def test_list_requests_returns_503(self, test_client):
        response = test_client.get("/api/v1/requests")
        assert response.status_code == 503

    def test_get_request_returns_503(self, test_client):
        response = test_client.get("/api/v1/requests/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 503

    def test_list_decisions_returns_503(self, test_client):
        response = test_client.get("/api/v1/decisions")
        assert response.status_code == 503

    def test_get_decision_returns_503(self, test_client):
        response = test_client.get("/api/v1/decisions/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 503

    def test_approve_returns_503(self, test_client):
        response = test_client.post(
            "/api/v1/decisions/00000000-0000-0000-0000-000000000000/approve",
            json={"approved_by": "admin"}
        )
        assert response.status_code == 503

    def test_backends_returns_503(self, test_client):
        response = test_client.get("/api/v1/backends")
        assert response.status_code == 503

    def test_routing_rules_returns_503(self, test_client):
        response = test_client.get("/api/v1/routing-rules")
        assert response.status_code == 503

    def test_cost_summary_returns_503(self, test_client):
        response = test_client.get("/api/v1/cost-summary")
        assert response.status_code == 503

    def test_routing_distribution_returns_503(self, test_client):
        response = test_client.get("/api/v1/analytics/routing-distribution")
        assert response.status_code == 503

    def test_latency_percentiles_returns_503(self, test_client):
        response = test_client.get("/api/v1/analytics/latency-percentiles")
        assert response.status_code == 503

    def test_governance_summary_returns_503(self, test_client):
        response = test_client.get("/api/v1/analytics/governance-summary")
        assert response.status_code == 503


class TestAPIValidation:
    """Test API input validation"""

    def test_invalid_task_returns_400(self, test_client):
        response = test_client.post("/v1/route", json={"task": "invalid_task"})
        assert response.status_code == 400
        assert "Unknown task" in response.json()["detail"]

    def test_valid_task_accepted(self, test_client):
        response = test_client.post("/v1/route", json={
            "task": "completion", "prompt": "test", "model_size_b": 1
        })
        # Will get 502 (backend unreachable) but NOT 400
        assert response.status_code != 400


class TestRoutingEndpoints:
    """Test routing info endpoints"""

    def test_list_routes_returns_200(self, test_client):
        response = test_client.get("/v1/routes")
        assert response.status_code == 200
        data = response.json()
        assert "routes" in data
        assert len(data["routes"]) >= 3

    def test_list_backends_returns_200(self, test_client):
        response = test_client.get("/v1/backends")
        assert response.status_code == 200
        data = response.json()
        assert "backends" in data
        assert len(data["backends"]) >= 3

    def test_backends_have_required_fields(self, test_client):
        response = test_client.get("/v1/backends")
        for b in response.json()["backends"]:
            assert "name" in b
            assert "url" in b
            assert "accelerator" in b
            assert "capabilities" in b

    def test_metrics_returns_prometheus_format(self, test_client):
        response = test_client.get("/metrics")
        assert response.status_code == 200
        assert 'gateway_' in response.text or 'HELP' in response.text


class TestGatewayDBIntegration:
    """Test that gateway router integrates with DB correctly"""

    def test_router_imports_db(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'import db' in content

    def test_router_mounts_api(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'include_router' in content

    def test_router_connects_db_on_startup(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'db.connect' in content

    def test_router_persists_requests(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'insert_request' in content

    def test_router_disconnects_on_shutdown(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'db.disconnect' in content


class TestAPIHardening:
    """API module hardening tests"""

    def test_api_has_uuid_path_types(self, project_root):
        """api.py should use UUID type for path parameters"""
        content = (project_root / "gateway" / "api.py").read_text()
        assert 'UUID' in content, "Should import and use UUID for path params"

    def test_approve_uses_post_body(self, project_root):
        """approve endpoint should use POST body, not query string for approved_by"""
        content = (project_root / "gateway" / "api.py").read_text()
        import re
        # approved_by should not be in Query()
        query_pattern = re.search(r'approved_by.*Query\(', content)
        assert query_pattern is None, \
            "approved_by should be in POST body, not Query parameter"
