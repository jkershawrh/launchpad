#!/usr/bin/env python3
"""
Tests for Frontend Dashboard (Stage 11)

Validates project structure, page files, API integration,
container, and deployment readiness.
"""

import subprocess
import json
import pytest
import yaml
from pathlib import Path


@pytest.fixture
def frontend_dir(project_root) -> Path:
    return project_root / "frontend"


@pytest.fixture
def src_dir(frontend_dir) -> Path:
    return frontend_dir / "src"


class TestProjectStructure:
    """Test Vite + React + TypeScript project structure"""

    def test_package_json_exists(self, frontend_dir):
        assert (frontend_dir / "package.json").exists()

    def test_vite_config_exists(self, frontend_dir):
        assert (frontend_dir / "vite.config.ts").exists()

    def test_tsconfig_exists(self, frontend_dir):
        assert (frontend_dir / "tsconfig.json").exists()

    def test_tsconfig_has_strict_mode(self, frontend_dir):
        with open(frontend_dir / "tsconfig.json") as f:
            config = json.load(f)
        assert config['compilerOptions'].get('strict') is True

    def test_env_example_exists(self, frontend_dir):
        assert (frontend_dir / ".env.example").exists()


class TestPatternFlyInstalled:
    """Test PatternFly 6 is a dependency"""

    def test_patternfly_in_package_json(self, frontend_dir):
        with open(frontend_dir / "package.json") as f:
            pkg = json.load(f)
        deps = pkg.get('dependencies', {})
        assert '@patternfly/react-core' in deps


class TestPages:
    """Test all 7 story-driven pages exist"""

    @pytest.mark.parametrize("page", [
        "Overview.tsx",
        "Architecture.tsx",
        "TryIt.tsx",
        "UseCases.tsx",
        "Operations.tsx",
        "GovernanceAudit.tsx",
        "Docs.tsx",
    ])
    def test_page_exists(self, src_dir, page):
        assert (src_dir / "pages" / page).exists(), f"Missing page: {page}"


class TestComponents:
    """Test reusable components exist"""

    @pytest.mark.parametrize("component", [
        "AppLayout.tsx",
        "HardwareBadge.tsx",
        "RequestFlowDiagram.tsx",
        "WorkflowDiagrams.tsx",
        "ErrorBoundary.tsx",
        "LiveWorkflow.tsx",
        "BuildYourOwn.tsx",
    ])
    def test_component_exists(self, src_dir, component):
        assert (src_dir / "components" / component).exists(), f"Missing component: {component}"


class TestAPIIntegration:
    """Test API integration layer"""

    def test_types_file_exists(self, src_dir):
        assert (src_dir / "api" / "types.ts").exists()

    def test_client_file_exists(self, src_dir):
        assert (src_dir / "api" / "client.ts").exists()

    def test_hooks_file_exists(self, src_dir):
        assert (src_dir / "api" / "hooks.ts").exists()

    def test_types_define_key_interfaces(self, src_dir):
        content = (src_dir / "api" / "types.ts").read_text()
        for interface in ['InferenceRequest', 'GovernanceDecision', 'BackendInfo',
                          'RoutingMetadata', 'RouteResponse', 'HealthStatus']:
            assert interface in content, f"Missing interface: {interface}"

    def test_hooks_define_key_hooks(self, src_dir):
        content = (src_dir / "api" / "hooks.ts").read_text()
        for hook in ['useHealth', 'useBackends', 'useRequests', 'useDecisions',
                      'useRoutingDistribution', 'useLatencyPercentiles',
                      'useApproveDecision', 'useRouteRequest']:
            assert hook in content, f"Missing hook: {hook}"

    def test_client_uses_relative_urls(self, src_dir):
        content = (src_dir / "api" / "client.ts").read_text()
        assert "|| ''" in content or "|| \"\"" in content, \
            "API client should default to empty string (relative URLs via nginx proxy)"


class TestContainer:
    """Test frontend container configuration"""

    def test_containerfile_exists(self, frontend_dir):
        assert (frontend_dir / "Containerfile").exists()

    def test_nginx_conf_exists(self, frontend_dir):
        assert (frontend_dir / "nginx.conf").exists()

    def test_containerfile_uses_ubi(self, frontend_dir):
        content = (frontend_dir / "Containerfile").read_text()
        assert 'ubi9' in content.lower(), "Should use UBI9 base"

    def test_containerfile_multistage(self, frontend_dir):
        content = (frontend_dir / "Containerfile").read_text()
        assert content.count('FROM') >= 2, "Should be multi-stage build"

    def test_nginx_proxies_api(self, frontend_dir):
        content = (frontend_dir / "nginx.conf").read_text()
        assert 'proxy_pass' in content
        assert 'gateway' in content
        assert '/v1/' in content
        assert '/api/' in content

    def test_nginx_logs_to_stderr(self, frontend_dir):
        content = (frontend_dir / "nginx.conf").read_text()
        assert '/dev/stderr' in content, "Should log to stderr for container compatibility"


class TestBranding:
    """Test Intel + Red Hat branding"""

    def test_intel_logo_exists(self, frontend_dir):
        assert (frontend_dir / "public" / "intel-logo.svg").exists()

    def test_redhat_logo_exists(self, frontend_dir):
        assert (frontend_dir / "public" / "redhat-logo.svg").exists()

    def test_layout_references_both_logos(self, src_dir):
        content = (src_dir / "components" / "AppLayout.tsx").read_text()
        assert 'intel-logo' in content, "Should display Intel logo"
        assert 'redhat-logo' in content, "Should display Red Hat logo"

    def test_title_includes_both_brands(self, src_dir):
        content = (src_dir / "components" / "AppLayout.tsx").read_text()
        assert 'Intel-Red Hat' in content, "Title should mention both Intel and Red Hat"

    def test_no_placeholder_urls(self, src_dir):
        for tsx_file in (src_dir / "pages").glob("*.tsx"):
            content = tsx_file.read_text()
            assert 'your-org' not in content, \
                f"Placeholder URL 'your-org' found in {tsx_file.name}"


class TestLiveWorkflow:
    """Test LiveWorkflow component for animated demo execution"""

    def test_live_workflow_exists(self, src_dir):
        assert (src_dir / "components" / "LiveWorkflow.tsx").exists()

    def test_live_workflow_has_step_states(self, src_dir):
        content = (src_dir / "components" / "LiveWorkflow.tsx").read_text()
        for state in ['pending', 'running', 'done', 'error']:
            assert f"'{state}'" in content, f"LiveWorkflow should handle '{state}' step state"

    def test_live_workflow_calls_gateway(self, src_dir):
        content = (src_dir / "components" / "LiveWorkflow.tsx").read_text()
        assert 'api.routeRequest' in content or 'routeRequest' in content, \
            "LiveWorkflow should call the gateway API per step"

    def test_live_workflow_shows_latency(self, src_dir):
        content = (src_dir / "components" / "LiveWorkflow.tsx").read_text()
        assert 'latency_ms' in content, "Should display per-step latency"

    def test_live_workflow_has_run_trigger(self, src_dir):
        content = (src_dir / "components" / "LiveWorkflow.tsx").read_text()
        assert 'runTrigger' in content, "Should support auto-run via runTrigger prop"

    def test_live_workflow_supports_local_steps(self, src_dir):
        content = (src_dir / "components" / "LiveWorkflow.tsx").read_text()
        assert 'local' in content, "Should handle local (non-gateway) steps"

    def test_live_workflow_has_animation(self, src_dir):
        content = (src_dir / "components" / "LiveWorkflow.tsx").read_text()
        assert 'pulse' in content or 'animation' in content, \
            "Should have CSS animation for running state"


class TestBuildYourOwn:
    """Test Build Your Own custom request component"""

    def test_build_your_own_exists(self, src_dir):
        assert (src_dir / "components" / "BuildYourOwn.tsx").exists()

    def test_has_task_selector(self, src_dir):
        content = (src_dir / "components" / "BuildYourOwn.tsx").read_text()
        assert 'completion' in content and 'embeddings' in content and 'classification' in content, \
            "Should have all task type options"

    def test_has_model_size_selector(self, src_dir):
        content = (src_dir / "components" / "BuildYourOwn.tsx").read_text()
        assert '1B' in content and '3B' in content and '7B' in content and '70B' in content, \
            "Should have model size options"

    def test_has_route_prediction(self, src_dir):
        content = (src_dir / "components" / "BuildYourOwn.tsx").read_text()
        assert 'predictRoute' in content or 'Predicted route' in content, \
            "Should show predicted routing decision before sending"

    def test_has_prediction_match_indicator(self, src_dir):
        content = (src_dir / "components" / "BuildYourOwn.tsx").read_text()
        assert 'Prediction matched' in content, \
            "Should indicate whether actual route matches prediction"

    def test_has_free_text_input(self, src_dir):
        content = (src_dir / "components" / "BuildYourOwn.tsx").read_text()
        assert 'TextArea' in content, "Should have free text prompt input"

    def test_calls_gateway_api(self, src_dir):
        content = (src_dir / "components" / "BuildYourOwn.tsx").read_text()
        assert 'api.routeRequest' in content, "Should call gateway API"


class TestTryItPage:
    """Test Try It page integrates all demo modes"""

    def test_try_it_has_workflow_tabs(self, src_dir):
        content = (src_dir / "pages" / "TryIt.tsx").read_text()
        assert 'Enterprise RAG' in content
        assert 'AIOps Copilot' in content
        assert 'Governed Agent' in content

    def test_try_it_has_build_your_own_tab(self, src_dir):
        content = (src_dir / "pages" / "TryIt.tsx").read_text()
        assert 'Build Your Own' in content
        assert 'BuildYourOwn' in content

    def test_try_it_uses_live_workflow(self, src_dir):
        content = (src_dir / "pages" / "TryIt.tsx").read_text()
        assert 'LiveWorkflow' in content

    def test_try_it_has_four_tabs(self, src_dir):
        content = (src_dir / "pages" / "TryIt.tsx").read_text()
        tab_count = content.count('eventKey=')
        assert tab_count >= 4, f"Should have 4 tabs, found {tab_count}"


class TestFrontendSecurity:
    """Security hardening tests for frontend"""

    def test_build_your_own_has_abort_controller(self, src_dir):
        """BuildYourOwn should use AbortController for race prevention"""
        content = (src_dir / "components" / "BuildYourOwn.tsx").read_text()
        assert 'AbortController' in content, \
            "BuildYourOwn should use AbortController"

    def test_live_workflow_has_abort_controller(self, src_dir):
        """LiveWorkflow should use AbortController"""
        content = (src_dir / "components" / "LiveWorkflow.tsx").read_text()
        assert 'AbortController' in content, \
            "LiveWorkflow should use AbortController"

    def test_nginx_has_csp_header(self, frontend_dir):
        """nginx should have Content-Security-Policy header"""
        content = (frontend_dir / "nginx.conf").read_text()
        assert 'Content-Security-Policy' in content

    def test_nginx_has_hsts(self, frontend_dir):
        """nginx should have HSTS header"""
        content = (frontend_dir / "nginx.conf").read_text()
        assert 'Strict-Transport-Security' in content

    def test_nginx_has_xframe_options(self, frontend_dir):
        """nginx should have X-Frame-Options"""
        content = (frontend_dir / "nginx.conf").read_text()
        assert 'X-Frame-Options' in content

    def test_nginx_has_nosniff(self, frontend_dir):
        """nginx should have X-Content-Type-Options nosniff"""
        content = (frontend_dir / "nginx.conf").read_text()
        assert 'X-Content-Type-Options' in content

    def test_metrics_restricted(self, frontend_dir):
        """nginx /metrics should be restricted"""
        content = (frontend_dir / "nginx.conf").read_text()
        assert 'internal' in content or 'deny all' in content, \
            "/metrics should be restricted"

    def test_client_has_auth_support(self, src_dir):
        """API client should support auth headers"""
        content = (src_dir / "api" / "client.ts").read_text()
        has_auth = ('Authorization' in content or 'X-API-Key' in content
                    or 'AUTH_TOKEN' in content)
        assert has_auth, "API client should support authentication"


class TestFrontendCodeQuality:
    """Code quality tests for frontend"""

    def test_approve_decision_uses_post_body(self, src_dir):
        """approveDecision should use POST body, not query string"""
        content = (src_dir / "api" / "client.ts").read_text()
        assert 'approved_by=' not in content, \
            "approved_by should be in POST body, not query string"

    def test_routes_typed(self, src_dir):
        """Routes should use typed interface, not unknown[]"""
        types_content = (src_dir / "api" / "types.ts").read_text()
        assert 'Route' in types_content, \
            "Should define Route interface in types.ts"

    def test_no_unused_requests_in_overview(self, src_dir):
        """Overview should not have unused useRequests"""
        content = (src_dir / "pages" / "Overview.tsx").read_text()
        assert 'useRequests' not in content, \
            "Overview should not import unused useRequests"

    def test_no_dead_risk_colors(self, src_dir):
        """GovernanceAudit should not have unused riskColors"""
        content = (src_dir / "pages" / "GovernanceAudit.tsx").read_text()
        if 'riskColors' in content:
            # If defined, it must be used (not just defined)
            lines = content.split('\n')
            def_line = None
            usage_count = 0
            for i, line in enumerate(lines):
                if 'riskColors' in line and ('const' in line or 'let' in line):
                    def_line = i
                elif 'riskColors' in line:
                    usage_count += 1
            assert usage_count > 0 or def_line is None, \
                "riskColors is defined but never used"

    def test_tsconfig_no_unused_locals(self, frontend_dir):
        """tsconfig should have noUnusedLocals: true"""
        import json
        with open(frontend_dir / "tsconfig.json") as f:
            config = json.load(f)
        assert config['compilerOptions'].get('noUnusedLocals') is True

    def test_tsconfig_no_unused_parameters(self, frontend_dir):
        """tsconfig should have noUnusedParameters: true"""
        import json
        with open(frontend_dir / "tsconfig.json") as f:
            config = json.load(f)
        assert config['compilerOptions'].get('noUnusedParameters') is True

    def test_error_boundary_has_catch(self, src_dir):
        """ErrorBoundary should have componentDidCatch"""
        content = (src_dir / "components" / "ErrorBoundary.tsx").read_text()
        assert 'componentDidCatch' in content, \
            "ErrorBoundary should log errors via componentDidCatch"

    def test_react_in_dependencies(self, frontend_dir):
        """react and react-dom should be in dependencies"""
        import json
        with open(frontend_dir / "package.json") as f:
            pkg = json.load(f)
        deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
        assert 'react' in deps, "react should be in dependencies"
        assert 'react-dom' in deps, "react-dom should be in dependencies"
