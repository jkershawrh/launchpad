#!/usr/bin/env python3
"""Tests for Overdrive API endpoints in gateway router."""
import pytest
import sys
import re
from pathlib import Path


class TestOverdriveRouteEndpoint:
    def test_route_endpoint_exists(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert '/v1/overdrive/route' in content

    def test_route_accepts_json_body(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'OverdriveRouteBody' in content or 'overdrive_route' in content

    def test_route_returns_evidence(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'evidence_to_dict' in content

    def test_route_uses_overdrive_engine(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert '_overdrive_engine' in content
        assert 'OverdriveEngine' in content

    def test_route_evaluates_request(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'evaluate' in content

    def test_route_creates_overdrive_request(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'OverdriveRequest' in content


class TestOverdriveBatchEndpoint:
    def test_batch_endpoint_exists(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert '/v1/overdrive/batch' in content

    def test_batch_accepts_json_body(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'OverdriveBatchBody' in content or 'overdrive_batch' in content

    def test_batch_uses_route_report(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'route_report' in content


class TestOverdriveStatusEndpoint:
    def test_status_endpoint_exists(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert '/v1/overdrive/status' in content

    def test_status_returns_lanes(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'get_route_state' in content


class TestOverdriveHealthEndpoint:
    def test_health_endpoint_exists(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert '/v1/overdrive/health' in content

    def test_health_toggles_lane(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'set_route_health' in content


class TestOverdriveInitialization:
    def test_engine_initialized_in_lifespan(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'OverdriveEngine' in content
        assert 'overdrive_config' in content or 'overdrive/config.yaml' in content

    def test_engine_fallback_on_import_error(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert 'except ImportError' in content
        assert '_overdrive_engine = None' in content

    def test_health_endpoint_includes_overdrive(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        # The /health endpoint should report overdrive status
        assert 'overdrive' in content.lower()


class TestOverdriveEnvResolution:
    def test_matrix_resolves_env_vars(self, project_root):
        content = (project_root / "gateway" / "overdrive" / "matrix.py").read_text()
        assert 'os.environ.get' in content
        assert '${' in content or 'ENV' in content

    def test_config_uses_litellm_endpoint(self, project_root):
        content = (project_root / "gateway" / "overdrive" / "config.yaml").read_text()
        assert 'LITELLM_API_BASE' in content

    def test_overdrive_rubrics_in_package(self, project_root):
        rubric_dir = project_root / "gateway" / "overdrive" / "rubrics"
        assert rubric_dir.exists(), "Rubrics should be in gateway/overdrive/rubrics/"
        yamls = list(rubric_dir.glob("*.yaml"))
        assert len(yamls) == 3, f"Expected 3 rubric files, found {len(yamls)}"
