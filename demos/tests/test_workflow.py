#!/usr/bin/env python3
"""
Tests for Workflow Routing Patterns

Validates the multi-step inference routing across hardware tiers —
the key demo differentiator. Tests config, POC pipeline structures,
trace metadata, and frontend visualization components.
"""

import subprocess
import pytest
import yaml
from pathlib import Path


@pytest.fixture
def gateway_dir(project_root) -> Path:
    return project_root / "gateway"


@pytest.fixture
def frontend_dir(project_root) -> Path:
    return project_root / "frontend" / "src"


class TestRoutingConfig:
    """Test that routing config defines complete task→backend mappings"""

    def test_config_has_three_backends(self, gateway_dir):
        with open(gateway_dir / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert len(config['backends']) >= 3

    def test_config_has_five_routes(self, gateway_dir):
        with open(gateway_dir / "config.yaml") as f:
            config = yaml.safe_load(f)
        assert len(config['routes']) >= 5

    def test_every_route_has_reason(self, gateway_dir):
        with open(gateway_dir / "config.yaml") as f:
            config = yaml.safe_load(f)
        for route in config['routes']:
            assert 'reason' in route, f"Route for {route['task']} missing reason"

    def test_completion_has_conditional_routing(self, gateway_dir):
        with open(gateway_dir / "config.yaml") as f:
            config = yaml.safe_load(f)
        completion_routes = [r for r in config['routes'] if r['task'] == 'completion']
        assert len(completion_routes) > 0
        route = completion_routes[0]
        assert 'conditions' in route, "Completion should have size-based conditions"

    def test_local_config_exists(self, gateway_dir):
        assert (gateway_dir / "config.local.yaml").exists()

    def test_local_config_uses_compose_hostnames(self, gateway_dir):
        with open(gateway_dir / "config.local.yaml") as f:
            config = yaml.safe_load(f)
        urls = [b['url'] for b in config['backends']]
        assert any('cpu-inference' in u for u in urls), \
            "Local config should use podman-compose service names"
        assert not any('.svc.cluster.local' in u for u in urls), \
            "Local config should NOT use cluster DNS"

    def test_config_path_env_supported(self, gateway_dir):
        content = (gateway_dir / "routing_policy.py").read_text()
        assert 'CONFIG_PATH' in content, "Should support CONFIG_PATH environment variable"


class TestMultiStepPipelines:
    """Test that POC apps implement multi-step routing across hardware tiers"""

    def test_rag_chains_four_steps(self, project_root):
        content = (project_root / "pocs" / "enterprise-rag" / "app.py").read_text()
        assert 'step_embed' in content
        assert 'step_search' in content
        assert 'step_rerank' in content
        assert 'step_generate' in content

    def test_rag_uses_multiple_task_types(self, project_root):
        content = (project_root / "pocs" / "enterprise-rag" / "app.py").read_text()
        assert '"embeddings"' in content
        assert '"reranking"' in content
        assert '"completion"' in content

    def test_aiops_chains_four_steps(self, project_root):
        content = (project_root / "pocs" / "aiops-copilot" / "app.py").read_text()
        assert 'step_classify' in content
        assert 'step_correlate' in content
        assert 'step_generate_rca' in content
        assert 'step_governance' in content

    def test_agent_chains_four_steps(self, project_root):
        content = (project_root / "pocs" / "governed-agent" / "app.py").read_text()
        assert 'step_classify_intent' in content
        assert 'step_risk_score' in content
        assert 'step_plan' in content
        assert 'step_policy_check' in content

    def test_all_pocs_have_mock_mode(self, project_root):
        for poc in ['enterprise-rag', 'aiops-copilot', 'governed-agent']:
            content = (project_root / "pocs" / poc / "app.py").read_text()
            assert 'MOCK_MODE' in content, f"{poc} should support mock mode"
            assert '--mock' in content, f"{poc} should have --mock flag"


class TestTraceMetadata:
    """Test that routing responses include proper metadata"""

    def test_router_returns_routing_metadata(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'RoutingMetadata' in content
        assert 'selected_backend' in content
        assert 'accelerator' in content
        assert 'reason' in content
        assert 'latency_ms' in content
        assert 'cost_estimate_per_1k_tokens' in content

    def test_pocs_capture_per_step_trace(self, project_root):
        for poc in ['enterprise-rag', 'aiops-copilot', 'governed-agent']:
            content = (project_root / "pocs" / poc / "app.py").read_text()
            assert 'trace' in content, f"{poc} should build a trace array"
            assert "'backend'" in content or '"backend"' in content, \
                f"{poc} trace should include backend per step"


class TestVisualizationComponents:
    """Test that frontend diagram components exist and are correct"""

    def test_request_flow_diagram_exists(self, frontend_dir):
        assert (frontend_dir / "components" / "RequestFlowDiagram.tsx").exists()

    def test_request_flow_has_aria_label(self, frontend_dir):
        content = (frontend_dir / "components" / "RequestFlowDiagram.tsx").read_text()
        assert 'aria-label' in content, "Diagram should have ARIA label for accessibility"

    def test_request_flow_shows_both_tiers(self, frontend_dir):
        content = (frontend_dir / "components" / "RequestFlowDiagram.tsx").read_text()
        assert 'Xeon 6' in content, "Should show Xeon 6 tier"
        assert 'Gaudi' in content, "Should show Gaudi tier"

    def test_workflow_diagrams_exists(self, frontend_dir):
        assert (frontend_dir / "components" / "WorkflowDiagrams.tsx").exists()

    def test_workflow_diagrams_has_aria_label(self, frontend_dir):
        content = (frontend_dir / "components" / "WorkflowDiagrams.tsx").read_text()
        assert 'aria-label' in content, "Workflow diagrams should have ARIA label"

    def test_workflow_diagrams_shows_three_pocs(self, frontend_dir):
        content = (frontend_dir / "components" / "WorkflowDiagrams.tsx").read_text()
        assert 'Enterprise RAG' in content
        assert 'AIOps Copilot' in content
        assert 'Governed Agent' in content

    def test_hardware_badge_exists(self, frontend_dir):
        assert (frontend_dir / "components" / "HardwareBadge.tsx").exists()

    def test_hardware_badge_has_xeon_and_gaudi(self, frontend_dir):
        content = (frontend_dir / "components" / "HardwareBadge.tsx").read_text()
        assert 'xeon6' in content
        assert 'gaudi' in content
        assert 'Xeon 6' in content
        assert 'Gaudi' in content


class TestRAGPipeline:
    """Tests for end-to-end RAG pipeline functionality"""

    def test_vector_search_not_local(self, frontend_dir):
        """RAG Vector Search step should call the gateway, not be local"""
        content = (frontend_dir / "pages" / "TryIt.tsx").read_text()
        import re
        search_step = re.search(r"label:\s*'Vector Search'.*?}", content, re.DOTALL)
        assert search_step, "Should have a Vector Search step"
        assert 'local: true' not in search_step.group(), \
            "Vector Search should not be marked local: true"

    def test_search_task_in_gateway(self, project_root):
        """Gateway should support 'search' as a valid task"""
        content = (project_root / "gateway" / "router.py").read_text()
        assert "'search'" in content or '"search"' in content, \
            "search should be in VALID_TASKS"

    def test_knowledge_base_exists(self, project_root):
        """Local inference should have a knowledge base corpus"""
        content = (project_root / "gateway" / "local_inference.py").read_text()
        assert 'KNOWLEDGE_BASE' in content, \
            "Should have a KNOWLEDGE_BASE for vector search"

    def test_vector_search_function_exists(self, project_root):
        """Local inference should have a vector_search function"""
        content = (project_root / "gateway" / "local_inference.py").read_text()
        assert 'async def vector_search(' in content, \
            "Should have a vector_search function"

    def test_step_chaining_in_workflow(self, frontend_dir):
        """LiveWorkflow should chain search results into generate prompt"""
        content = (frontend_dir / "components" / "LiveWorkflow.tsx").read_text()
        assert 'searchContext' in content, \
            "Should pass search context to completion step"

    def test_search_route_in_config(self, project_root):
        """Config should have a route for the search task"""
        config = yaml.safe_load(
            (project_root / "gateway" / "config.local.yaml").read_text()
        )
        routes = config.get('routes', [])
        search_routes = [r for r in routes if r.get('task') == 'search']
        assert len(search_routes) > 0, \
            "Should have a search route in config"
