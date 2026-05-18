#!/usr/bin/env python3
"""
Tests for Observability Stack

TDD Phase: RED/GREEN - Validates ServiceMonitor and Grafana dashboard.
"""

import json
import pytest
import yaml
from pathlib import Path


@pytest.fixture
def obs_dir(project_root) -> Path:
    return project_root / "deploy" / "observability"


class TestObservabilityStructure:
    """Test observability manifest structure"""

    def test_observability_directory_exists(self, obs_dir):
        """Observability deploy directory should exist"""
        assert obs_dir.exists(), "deploy/observability/ not found"

    def test_servicemonitor_exists(self, obs_dir):
        """ServiceMonitor manifest should exist"""
        assert (obs_dir / "servicemonitor.yaml").exists()

    def test_grafana_dashboard_exists(self, obs_dir):
        """Grafana dashboard JSON should exist"""
        assert (obs_dir / "grafana-dashboard.json").exists()

    def test_kustomization_exists(self, obs_dir):
        """Kustomization file should exist"""
        assert (obs_dir / "kustomization.yaml").exists()


class TestServiceMonitor:
    """Test ServiceMonitor configuration"""

    def test_servicemonitor_is_valid_yaml(self, obs_dir):
        """ServiceMonitor should be valid YAML"""
        sm_file = obs_dir / "servicemonitor.yaml"
        if not sm_file.exists():
            pytest.skip("servicemonitor.yaml not created yet")
        with open(sm_file) as f:
            doc = yaml.safe_load(f)
        assert doc['kind'] == 'ServiceMonitor'

    def test_servicemonitor_targets_gateway(self, obs_dir):
        """ServiceMonitor should target the inference gateway"""
        sm_file = obs_dir / "servicemonitor.yaml"
        if not sm_file.exists():
            pytest.skip("servicemonitor.yaml not created yet")
        with open(sm_file) as f:
            doc = yaml.safe_load(f)
        selector = doc['spec']['selector']['matchLabels']
        assert 'inference-gateway' in str(selector), \
            "Should target inference-gateway"

    def test_servicemonitor_scrapes_metrics(self, obs_dir):
        """ServiceMonitor should scrape /metrics endpoint"""
        sm_file = obs_dir / "servicemonitor.yaml"
        if not sm_file.exists():
            pytest.skip("servicemonitor.yaml not created yet")
        with open(sm_file) as f:
            doc = yaml.safe_load(f)
        endpoints = doc['spec']['endpoints']
        paths = [e.get('path', '') for e in endpoints]
        assert '/metrics' in paths, "Should scrape /metrics"


class TestGrafanaDashboard:
    """Test Grafana dashboard JSON"""

    def test_dashboard_is_valid_json(self, obs_dir):
        """Dashboard should be valid JSON"""
        dash_file = obs_dir / "grafana-dashboard.json"
        if not dash_file.exists():
            pytest.skip("grafana-dashboard.json not created yet")
        with open(dash_file) as f:
            doc = json.load(f)
        assert 'panels' in doc, "Dashboard should have panels"

    def test_dashboard_has_panels(self, obs_dir):
        """Dashboard should have visualization panels"""
        dash_file = obs_dir / "grafana-dashboard.json"
        if not dash_file.exists():
            pytest.skip("grafana-dashboard.json not created yet")
        with open(dash_file) as f:
            doc = json.load(f)
        assert len(doc['panels']) >= 4, \
            "Dashboard should have at least 4 panels"

    def test_dashboard_has_latency_panel(self, obs_dir):
        """Dashboard should include a latency panel"""
        dash_file = obs_dir / "grafana-dashboard.json"
        if not dash_file.exists():
            pytest.skip("grafana-dashboard.json not created yet")
        with open(dash_file) as f:
            doc = json.load(f)
        titles = [p.get('title', '').lower() for p in doc['panels']]
        assert any('latency' in t for t in titles), \
            "Should have a latency panel"

    def test_dashboard_has_routing_panel(self, obs_dir):
        """Dashboard should include a routing decision panel"""
        dash_file = obs_dir / "grafana-dashboard.json"
        if not dash_file.exists():
            pytest.skip("grafana-dashboard.json not created yet")
        with open(dash_file) as f:
            doc = json.load(f)
        titles = [p.get('title', '').lower() for p in doc['panels']]
        assert any('routing' in t or 'backend' in t for t in titles), \
            "Should have a routing/backend panel"

    def test_dashboard_queries_gateway_metrics(self, obs_dir):
        """Dashboard should query gateway_ Prometheus metrics"""
        dash_file = obs_dir / "grafana-dashboard.json"
        if not dash_file.exists():
            pytest.skip("grafana-dashboard.json not created yet")
        with open(dash_file) as f:
            content = f.read()
        assert 'gateway_' in content, \
            "Dashboard queries should reference gateway_ metrics"
