#!/usr/bin/env python3
"""
Tests for manifest hardening across all deployment components.
Validates security contexts, network policies, and reliability features.
"""

import pytest
import yaml
import json
from pathlib import Path


@pytest.fixture
def deploy_dir(project_root) -> Path:
    return project_root / "deploy"


@pytest.fixture
def gateway_deploy(deploy_dir) -> Path:
    return deploy_dir / "gateway"


@pytest.fixture
def cpu_deploy(deploy_dir) -> Path:
    return deploy_dir / "cpu-inference"


@pytest.fixture
def gaudi_deploy(deploy_dir) -> Path:
    return deploy_dir / "gaudi-inference"


class TestNetworkPolicyHardening:
    """Network policy consistency tests"""

    def test_gateway_egress_to_database(self, gateway_deploy):
        """Gateway should have egress rule to database namespace"""
        netpol = yaml.safe_load((gateway_deploy / "network-policy.yaml").read_text())
        egress_rules = netpol['spec'].get('egress', [])
        db_egress = False
        for rule in egress_rules:
            for to in rule.get('to', []):
                ns = to.get('namespaceSelector', {}).get('matchLabels', {})
                if 'intel-rh-database' in str(ns):
                    ports = [p.get('port') for p in rule.get('ports', [])]
                    if 5432 in ports:
                        db_egress = True
        assert db_egress, "Gateway must have egress to database on port 5432"

    def test_cpu_dns_namespace_selector(self, cpu_deploy):
        """CPU inference DNS egress should use kubernetes.io/metadata.name"""
        netpol = yaml.safe_load((cpu_deploy / "network-policy.yaml").read_text())
        content = (cpu_deploy / "network-policy.yaml").read_text()
        assert 'kubernetes.io/metadata.name: openshift-dns' in content, \
            "DNS egress should use kubernetes.io/metadata.name"
        assert '\n        name: openshift-dns' not in content or \
            'kubernetes.io/metadata.name' in content

    def test_gaudi_dns_namespace_selector(self, gaudi_deploy):
        """Gaudi inference DNS egress should use kubernetes.io/metadata.name"""
        content = (gaudi_deploy / "network-policy.yaml").read_text()
        assert 'kubernetes.io/metadata.name: openshift-dns' in content

    def test_ingress_labels_consistent(self, deploy_dir):
        """All network policies should use the same ingress label"""
        target_label = 'policy-group.network.openshift.io/ingress'
        for subdir in ['cpu-inference', 'gaudi-inference', 'gateway', 'openvino-cpu']:
            netpol_path = deploy_dir / subdir / "network-policy.yaml"
            if netpol_path.exists():
                content = netpol_path.read_text()
                if 'ingress' in content.lower():
                    assert target_label in content, \
                        f"{subdir}/network-policy.yaml should use {target_label}"


class TestSecurityContextHardening:
    """Security context tests across all deployments"""

    def test_no_hardcoded_run_as_user(self, deploy_dir):
        """No manifest should hardcode runAsUser: 1001"""
        for yaml_file in deploy_dir.rglob("*.yaml"):
            if yaml_file.name == 'kustomization.yaml':
                continue
            content = yaml_file.read_text()
            if 'runAsUser: 1001' in content:
                pytest.fail(f"{yaml_file.relative_to(deploy_dir)} has hardcoded runAsUser: 1001")

    def test_gateway_read_only_root(self, gateway_deploy):
        """Gateway should have readOnlyRootFilesystem"""
        content = (gateway_deploy / "deployment.yaml").read_text()
        assert 'readOnlyRootFilesystem: true' in content

    def test_database_security_context(self, deploy_dir):
        """Database should have security context"""
        content = (deploy_dir / "database" / "deployment.yaml").read_text()
        assert 'runAsNonRoot: true' in content
        assert 'allowPrivilegeEscalation: false' in content

    def test_database_recreate_strategy(self, deploy_dir):
        """Database should use Recreate strategy"""
        doc = yaml.safe_load((deploy_dir / "database" / "deployment.yaml").read_text())
        strategy = doc['spec'].get('strategy', {}).get('type', 'RollingUpdate')
        assert strategy == 'Recreate', \
            f"Database should use Recreate strategy, got {strategy}"

    def test_placeholder_images_replaced(self, deploy_dir):
        """No [TBD] placeholder images should remain"""
        for yaml_file in deploy_dir.rglob("*.yaml"):
            content = yaml_file.read_text()
            assert '[TBD' not in content, \
                f"{yaml_file.relative_to(deploy_dir)} still has [TBD] placeholder"


class TestReliabilityFeatures:
    """Reliability and availability tests"""

    def test_gateway_has_pdb(self, gateway_deploy):
        """Gateway should have a PodDisruptionBudget"""
        assert (gateway_deploy / "pdb.yaml").exists(), \
            "deploy/gateway/pdb.yaml should exist"

    def test_gateway_has_hpa(self, gateway_deploy):
        """Gateway should have a HorizontalPodAutoscaler"""
        assert (gateway_deploy / "hpa.yaml").exists(), \
            "deploy/gateway/hpa.yaml should exist"

    def test_gateway_has_anti_affinity(self, gateway_deploy):
        """Gateway should have pod anti-affinity"""
        content = (gateway_deploy / "deployment.yaml").read_text()
        assert 'podAntiAffinity' in content

    def test_observability_has_namespace(self, deploy_dir):
        """Observability kustomization should specify namespace"""
        content = (deploy_dir / "observability" / "kustomization.yaml").read_text()
        assert 'namespace:' in content


class TestObservabilityCorrectness:
    """Observability configuration tests"""

    def test_error_rate_promql_correct(self, deploy_dir):
        """Grafana error rate should not use subtraction pattern"""
        dashboard_path = deploy_dir / "observability" / "grafana-dashboard.json"
        content = dashboard_path.read_text()
        data = json.loads(content)
        for panel in data.get('panels', []):
            title = panel.get('title', '')
            if 'error' in title.lower():
                for target in panel.get('targets', []):
                    expr = target.get('expr', '')
                    assert 'rate(' not in expr or '-' not in expr or 'status' in expr, \
                        f"Error rate panel uses subtraction pattern: {expr}"
