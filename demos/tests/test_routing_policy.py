#!/usr/bin/env python3
"""
Tests for Inference Routing Policy Engine

TDD Phase: RED - Tests written first.
The routing policy decides which backend handles each request
based on task type, model size, latency requirements, and cost.
"""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def gateway_dir(project_root) -> Path:
    return project_root / "gateway"


@pytest.fixture
def config_file(gateway_dir) -> Path:
    return gateway_dir / "config.yaml"


@pytest.fixture
def routing_config(config_file):
    if not config_file.exists():
        pytest.skip("config.yaml not created yet")
    with open(config_file) as f:
        return yaml.safe_load(f)


class TestConfigStructure:
    """Test routing config file structure"""

    def test_config_file_exists(self, config_file):
        """Routing config should exist"""
        assert config_file.exists(), "gateway/config.yaml not found"

    def test_config_is_valid_yaml(self, config_file):
        """Config should parse as valid YAML"""
        if not config_file.exists():
            pytest.skip("config.yaml not created yet")
        with open(config_file) as f:
            doc = yaml.safe_load(f)
        assert doc is not None, "Config parsed as empty"

    def test_config_has_backends(self, routing_config):
        """Config should define available backends"""
        assert 'backends' in routing_config, "Config must define backends"
        assert len(routing_config['backends']) >= 2, \
            "Should have at least CPU and Gaudi backends"

    def test_config_has_routes(self, routing_config):
        """Config should define routing rules"""
        assert 'routes' in routing_config, "Config must define routes"
        assert len(routing_config['routes']) >= 3, \
            "Should have routes for at least embeddings, classification, and completion"

    def test_backends_have_required_fields(self, routing_config):
        """Each backend must have name, url, and capabilities"""
        for backend in routing_config['backends']:
            assert 'name' in backend, f"Backend missing name: {backend}"
            assert 'url' in backend, f"Backend {backend.get('name')} missing url"
            assert 'capabilities' in backend, \
                f"Backend {backend.get('name')} missing capabilities"

    def test_routes_have_required_fields(self, routing_config):
        """Each route must have task and target backend"""
        for route in routing_config['routes']:
            assert 'task' in route, f"Route missing task: {route}"
            assert 'backend' in route or 'conditions' in route, \
                f"Route {route.get('task')} needs either backend or conditions"


class TestRoutingPolicyModule:
    """Test the routing policy Python module"""

    def test_routing_policy_module_exists(self, gateway_dir):
        """routing_policy.py should exist"""
        policy_file = gateway_dir / "routing_policy.py"
        assert policy_file.exists(), "gateway/routing_policy.py not found"

    def test_routing_policy_imports(self, gateway_dir):
        """Module should import without errors"""
        import subprocess
        policy_file = gateway_dir / "routing_policy.py"
        if not policy_file.exists():
            pytest.skip("routing_policy.py not created yet")
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(policy_file)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_routing_policy_has_route_function(self, gateway_dir):
        """Module should expose a route() function"""
        policy_file = gateway_dir / "routing_policy.py"
        if not policy_file.exists():
            pytest.skip("routing_policy.py not created yet")
        content = policy_file.read_text()
        assert 'def route(' in content, \
            "routing_policy.py must have a route() function"

    def test_routing_policy_has_load_config_function(self, gateway_dir):
        """Module should expose a load_config() function"""
        policy_file = gateway_dir / "routing_policy.py"
        if not policy_file.exists():
            pytest.skip("routing_policy.py not created yet")
        content = policy_file.read_text()
        assert 'def load_config(' in content, \
            "routing_policy.py must have a load_config() function"


class TestRoutingDecisions:
    """Test that routing produces correct decisions for each task type"""

    def test_embeddings_route_to_cpu(self, routing_config):
        """Embeddings should route to OpenVINO CPU backend"""
        embedding_routes = [
            r for r in routing_config['routes']
            if r['task'] == 'embeddings'
        ]
        assert len(embedding_routes) > 0, "No route for embeddings task"
        route = embedding_routes[0]
        backend = route.get('backend', '')
        assert 'openvino' in backend.lower() or 'cpu' in backend.lower(), \
            f"Embeddings should route to CPU/OpenVINO, got: {backend}"

    def test_classification_route_to_cpu(self, routing_config):
        """Classification should route to OpenVINO CPU backend"""
        routes = [r for r in routing_config['routes'] if r['task'] == 'classification']
        assert len(routes) > 0, "No route for classification task"
        backend = routes[0].get('backend', '')
        assert 'openvino' in backend.lower() or 'cpu' in backend.lower(), \
            f"Classification should route to CPU/OpenVINO, got: {backend}"

    def test_reranking_route_to_cpu(self, routing_config):
        """Reranking should route to OpenVINO CPU backend"""
        routes = [r for r in routing_config['routes'] if r['task'] == 'reranking']
        assert len(routes) > 0, "No route for reranking task"
        backend = routes[0].get('backend', '')
        assert 'openvino' in backend.lower() or 'cpu' in backend.lower(), \
            f"Reranking should route to CPU/OpenVINO, got: {backend}"

    def test_completion_has_conditional_routing(self, routing_config):
        """Completion should have conditional routing based on model size"""
        routes = [r for r in routing_config['routes'] if r['task'] == 'completion']
        assert len(routes) > 0, "No route for completion task"
        route = routes[0]
        has_conditions = 'conditions' in route
        has_backend = 'backend' in route
        assert has_conditions or has_backend, \
            "Completion route should have conditions or a default backend"

    def test_batch_generation_routes_to_gaudi(self, routing_config):
        """Batch generation should route to Gaudi backend"""
        routes = [r for r in routing_config['routes'] if r['task'] == 'batch_generation']
        assert len(routes) > 0, "No route for batch_generation task"
        backend = routes[0].get('backend', '')
        assert 'gaudi' in backend.lower(), \
            f"Batch generation should route to Gaudi, got: {backend}"

    def test_routes_have_reason(self, routing_config):
        """Each route should explain why it makes that routing decision"""
        for route in routing_config['routes']:
            assert 'reason' in route, \
                f"Route for {route.get('task')} missing 'reason' field"


class TestBackendDefinitions:
    """Test backend configuration"""

    def test_openvino_backend_defined(self, routing_config):
        """OpenVINO CPU backend should be defined"""
        names = [b['name'] for b in routing_config['backends']]
        assert any('openvino' in n.lower() for n in names), \
            "Should have an OpenVINO backend defined"

    def test_vllm_cpu_backend_defined(self, routing_config):
        """vLLM CPU backend should be defined"""
        names = [b['name'] for b in routing_config['backends']]
        assert any('cpu' in n.lower() and 'vllm' in n.lower() for n in names) or \
            any('cpu' in n.lower() and 'llm' in n.lower() for n in names), \
            "Should have a vLLM CPU backend defined"

    def test_gaudi_backend_defined(self, routing_config):
        """Gaudi GPU backend should be defined"""
        names = [b['name'] for b in routing_config['backends']]
        assert any('gaudi' in n.lower() for n in names), \
            "Should have a Gaudi backend defined"

    def test_backends_declare_capabilities(self, routing_config):
        """Each backend should declare its task capabilities"""
        for backend in routing_config['backends']:
            caps = backend.get('capabilities', [])
            assert len(caps) > 0, \
                f"Backend {backend['name']} has no capabilities declared"

    def test_backends_have_accelerator_info(self, routing_config):
        """Each backend should declare its accelerator type"""
        for backend in routing_config['backends']:
            assert 'accelerator' in backend, \
                f"Backend {backend['name']} missing accelerator field"


class TestFallbackRouting:
    """Tests for fallback field in routing decisions"""

    def test_config_local_routes_have_fallback(self, project_root):
        """config.local.yaml routes should have fallback: local"""
        config_path = project_root / "gateway" / "config.local.yaml"
        if not config_path.exists():
            pytest.skip("config.local.yaml not found")
        config = yaml.safe_load(config_path.read_text())
        routes = config.get('routes', [])
        has_fallback = any(r.get('fallback') for r in routes)
        assert has_fallback, "At least one route should have fallback: local"

    def test_routing_policy_extracts_fallback(self, project_root):
        """routing_policy.py should extract fallback from route config"""
        content = (project_root / "gateway" / "routing_policy.py").read_text()
        assert "fallback" in content, \
            "RoutingPolicy should handle fallback field"

    def test_routing_decision_fallback_populated(self, project_root):
        """RoutingPolicy.route() should populate fallback from config"""
        import sys
        gw_path = str(project_root / "gateway")
        sys.path.insert(0, gw_path)
        try:
            import importlib
            import routing_policy as rp
            importlib.reload(rp)
            config = yaml.safe_load((project_root / "gateway" / "config.local.yaml").read_text())
            policy = rp.RoutingPolicy(config)
            decision = policy.route("completion", model_size_b=1.0)
            assert decision.fallback is not None, \
                "Routing decision should have fallback set from config"
            assert decision.fallback == "local", \
                f"Expected fallback='local', got '{decision.fallback}'"
        finally:
            sys.path.remove(gw_path)
