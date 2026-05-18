#!/usr/bin/env python3
"""
Tests for Inference Gateway API

TDD Phase: RED - Tests written first.
The gateway is the single entry point for all inference requests.
It routes to the correct backend and returns routing metadata.
"""

import pytest
import subprocess
from pathlib import Path


@pytest.fixture
def gateway_dir(project_root) -> Path:
    return project_root / "gateway"


class TestGatewayStructure:
    """Test gateway file structure"""

    def test_gateway_directory_exists(self, gateway_dir):
        """Gateway directory should exist"""
        assert gateway_dir.exists(), "gateway/ directory not found"

    def test_router_module_exists(self, gateway_dir):
        """router.py should exist"""
        assert (gateway_dir / "router.py").exists(), "gateway/router.py not found"

    def test_routing_policy_exists(self, gateway_dir):
        """routing_policy.py should exist"""
        assert (gateway_dir / "routing_policy.py").exists(), \
            "gateway/routing_policy.py not found"

    def test_config_exists(self, gateway_dir):
        """config.yaml should exist"""
        assert (gateway_dir / "config.yaml").exists(), \
            "gateway/config.yaml not found"

    def test_containerfile_exists(self, gateway_dir):
        """Containerfile should exist"""
        assert (gateway_dir / "Containerfile").exists(), \
            "gateway/Containerfile not found"

    def test_requirements_exists(self, gateway_dir):
        """requirements.txt should exist"""
        assert (gateway_dir / "requirements.txt").exists(), \
            "gateway/requirements.txt not found"


class TestRouterModule:
    """Test router.py module"""

    def test_router_compiles(self, gateway_dir):
        """router.py should compile without errors"""
        router_file = gateway_dir / "router.py"
        if not router_file.exists():
            pytest.skip("router.py not created yet")
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(router_file)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_router_has_fastapi_app(self, gateway_dir):
        """router.py should define a FastAPI app"""
        router_file = gateway_dir / "router.py"
        if not router_file.exists():
            pytest.skip("router.py not created yet")
        content = router_file.read_text()
        assert 'FastAPI' in content, "router.py should use FastAPI"
        assert 'app = ' in content or 'app=' in content, \
            "router.py should create an app instance"

    def test_router_has_route_endpoint(self, gateway_dir):
        """router.py should have /v1/route endpoint"""
        router_file = gateway_dir / "router.py"
        if not router_file.exists():
            pytest.skip("router.py not created yet")
        content = router_file.read_text()
        assert '/v1/route' in content, "Should have /v1/route endpoint"

    def test_router_has_routes_endpoint(self, gateway_dir):
        """router.py should have /v1/routes listing endpoint"""
        router_file = gateway_dir / "router.py"
        if not router_file.exists():
            pytest.skip("router.py not created yet")
        content = router_file.read_text()
        assert '/v1/routes' in content, "Should have /v1/routes endpoint"

    def test_router_has_backends_endpoint(self, gateway_dir):
        """router.py should have /v1/backends endpoint"""
        router_file = gateway_dir / "router.py"
        if not router_file.exists():
            pytest.skip("router.py not created yet")
        content = router_file.read_text()
        assert '/v1/backends' in content, "Should have /v1/backends endpoint"

    def test_router_has_health_endpoint(self, gateway_dir):
        """router.py should have /health endpoint"""
        router_file = gateway_dir / "router.py"
        if not router_file.exists():
            pytest.skip("router.py not created yet")
        content = router_file.read_text()
        assert '/health' in content, "Should have /health endpoint"

    def test_router_has_metrics_endpoint(self, gateway_dir):
        """router.py should have /metrics endpoint"""
        router_file = gateway_dir / "router.py"
        if not router_file.exists():
            pytest.skip("router.py not created yet")
        content = router_file.read_text()
        assert '/metrics' in content, "Should have /metrics endpoint"


class TestContainerfile:
    """Test gateway container"""

    def test_containerfile_has_ubi_base(self, gateway_dir):
        """Should use UBI9 base image"""
        cf = gateway_dir / "Containerfile"
        if not cf.exists():
            pytest.skip("Containerfile not created yet")
        content = cf.read_text()
        assert 'ubi9' in content.lower() or 'ubi' in content.lower(), \
            "Should use Red Hat UBI base image"

    def test_containerfile_runs_nonroot(self, gateway_dir):
        """Should run as non-root user"""
        cf = gateway_dir / "Containerfile"
        if not cf.exists():
            pytest.skip("Containerfile not created yet")
        content = cf.read_text()
        assert 'USER' in content and '1001' in content, \
            "Should run as non-root user (1001)"

    def test_containerfile_exposes_port(self, gateway_dir):
        """Should expose the gateway port"""
        cf = gateway_dir / "Containerfile"
        if not cf.exists():
            pytest.skip("Containerfile not created yet")
        content = cf.read_text()
        assert 'EXPOSE' in content, "Should expose a port"


class TestRequirements:
    """Test gateway dependencies"""

    def test_requirements_has_fastapi(self, gateway_dir):
        """Should depend on FastAPI"""
        req = gateway_dir / "requirements.txt"
        if not req.exists():
            pytest.skip("requirements.txt not created yet")
        content = req.read_text().lower()
        assert 'fastapi' in content, "Should list fastapi as dependency"

    def test_requirements_has_httpx(self, gateway_dir):
        """Should depend on httpx for async backend calls"""
        req = gateway_dir / "requirements.txt"
        if not req.exists():
            pytest.skip("requirements.txt not created yet")
        content = req.read_text().lower()
        assert 'httpx' in content, "Should list httpx for backend forwarding"

    def test_requirements_has_prometheus(self, gateway_dir):
        """Should depend on prometheus_client for metrics"""
        req = gateway_dir / "requirements.txt"
        if not req.exists():
            pytest.skip("requirements.txt not created yet")
        content = req.read_text().lower()
        assert 'prometheus' in content, "Should list prometheus_client for metrics"


class TestGatewaySecurity:
    """Security hardening tests for gateway"""

    def test_router_has_api_key_dependency(self, gateway_dir):
        """router.py should have API key authentication"""
        content = (gateway_dir / "router.py").read_text()
        assert 'Depends(' in content, "Should use FastAPI Depends for auth"
        assert 'api_key' in content.lower() or 'API_KEY' in content, \
            "Should reference API key"

    def test_error_messages_no_internal_urls(self, gateway_dir):
        """Error responses should not leak internal service URLs"""
        content = (gateway_dir / "router.py").read_text()
        # Find HTTPException detail= strings and check for URL patterns
        import re
        details = re.findall(r'detail=f["\'].*?{.*?\.url.*?}', content)
        assert len(details) == 0, \
            f"HTTPException details should not contain backend URLs: {details}"

    def test_request_has_max_prompt_length(self, gateway_dir):
        """RouteRequest.prompt should have max_length constraint"""
        content = (gateway_dir / "router.py").read_text()
        assert 'max_length' in content, \
            "prompt field should have max_length constraint"

    def test_texts_typed_as_list_str(self, gateway_dir):
        """RouteRequest.texts should be typed as list[str], not bare list"""
        content = (gateway_dir / "router.py").read_text()
        assert 'list[str]' in content or 'List[str]' in content, \
            "texts should be typed as list[str]"
        # Should NOT have bare 'list' without type parameter for texts
        import re
        bare_list = re.search(r'texts.*Optional\[list\]', content)
        assert bare_list is None, "texts should not use bare list type"

    def test_has_rate_limiting(self, gateway_dir):
        """router.py should have rate limiting"""
        content = (gateway_dir / "router.py").read_text()
        has_rate = ('RateLimiter' in content or 'rate_limit' in content
                    or 'slowapi' in content or 'RATE_LIMIT' in content)
        assert has_rate, "Should have rate limiting"

    def test_has_cors_middleware(self, gateway_dir):
        """router.py should configure CORS"""
        content = (gateway_dir / "router.py").read_text()
        assert 'CORSMiddleware' in content, "Should have CORSMiddleware"

    def test_build_payload_no_silent_none(self, gateway_dir):
        """_build_payload should not silently return (None, None)"""
        content = (gateway_dir / "router.py").read_text()
        assert 'return None, None' not in content, \
            "_build_payload should raise on unknown task, not return None"


class TestGatewayResilience:
    """Resilience and reliability tests"""

    def test_health_check_probes_db(self, gateway_dir):
        """Health endpoint should probe database connectivity"""
        content = (gateway_dir / "router.py").read_text()
        # Find the health endpoint and check it probes DB
        assert 'is_connected' in content, \
            "Health endpoint should check db.is_connected()"

    def test_retry_fallback_on_failure(self, gateway_dir):
        """Should try fallback backend on primary failure"""
        content = (gateway_dir / "router.py").read_text()
        assert 'fallback' in content.lower(), \
            "Should implement fallback retry logic"


class TestLocalFallback:
    """Local model fallback tests"""

    def test_local_inference_module_exists(self, gateway_dir):
        """gateway/local_inference.py should exist"""
        assert (gateway_dir / "local_inference.py").exists(), \
            "gateway/local_inference.py not found"

    def test_local_inference_compiles(self, gateway_dir):
        """local_inference.py should compile without errors"""
        lf = gateway_dir / "local_inference.py"
        if not lf.exists():
            pytest.skip("local_inference.py not created yet")
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(lf)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_local_inference_has_env_toggle(self, gateway_dir):
        """local_inference should be enabled via LOCAL_FALLBACK_ENABLED"""
        lf = gateway_dir / "local_inference.py"
        if not lf.exists():
            pytest.skip("local_inference.py not created yet")
        content = lf.read_text()
        assert 'LOCAL_FALLBACK_ENABLED' in content, \
            "Should use LOCAL_FALLBACK_ENABLED env var"

    def test_local_inference_has_generate(self, gateway_dir):
        """local_inference should have a generate function"""
        lf = gateway_dir / "local_inference.py"
        if not lf.exists():
            pytest.skip("local_inference.py not created yet")
        content = lf.read_text()
        assert 'def generate(' in content, \
            "Should have a generate function"

    def test_local_inference_has_is_available(self, gateway_dir):
        """local_inference should have an is_available function"""
        lf = gateway_dir / "local_inference.py"
        if not lf.exists():
            pytest.skip("local_inference.py not created yet")
        content = lf.read_text()
        assert 'def is_available(' in content, \
            "Should have is_available function"

    def test_router_imports_local_inference(self, gateway_dir):
        """router.py should import local_inference"""
        content = (gateway_dir / "router.py").read_text()
        assert 'local_inference' in content, \
            "router.py should import or reference local_inference"

    def test_router_initializes_local_inference(self, gateway_dir):
        """router.py lifespan should initialize local inference"""
        content = (gateway_dir / "router.py").read_text()
        assert 'local_inference.initialize' in content, \
            "router.py should call local_inference.initialize() in lifespan"

    def test_router_local_fallback_path(self, gateway_dir):
        """router.py should call local_inference for fallback"""
        content = (gateway_dir / "router.py").read_text()
        assert 'local_inference.handle_task' in content, \
            "router.py should use local_inference.handle_task for fallback"

    def test_health_reports_local_fallback(self, gateway_dir):
        """Health endpoint should report local_fallback status"""
        content = (gateway_dir / "router.py").read_text()
        assert 'local_fallback' in content, \
            "Health endpoint should include local_fallback info"
