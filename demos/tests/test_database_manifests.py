#!/usr/bin/env python3
"""
Tests for Database Deploy Manifests (Stage 10)

Validates PostgreSQL deployment manifests and Ansible role.
"""

import pytest
import yaml
from pathlib import Path
from conftest import parse_k8s_memory_gi


@pytest.fixture
def db_deploy_dir(project_root) -> Path:
    return project_root / "deploy" / "database"


class TestDeployStructure:
    """Test database deploy directory"""

    def test_database_deploy_dir_exists(self, db_deploy_dir):
        assert db_deploy_dir.exists(), "deploy/database/ not found"

    def test_namespace_exists(self, db_deploy_dir):
        assert (db_deploy_dir / "namespace.yaml").exists()

    def test_deployment_exists(self, db_deploy_dir):
        assert (db_deploy_dir / "deployment.yaml").exists()

    def test_service_exists(self, db_deploy_dir):
        assert (db_deploy_dir / "service.yaml").exists()

    def test_pvc_exists(self, db_deploy_dir):
        assert (db_deploy_dir / "pvc.yaml").exists()

    def test_secret_exists(self, db_deploy_dir):
        assert (db_deploy_dir / "secret.yaml").exists()

    def test_network_policy_exists(self, db_deploy_dir):
        assert (db_deploy_dir / "network-policy.yaml").exists()

    def test_kustomization_exists(self, db_deploy_dir):
        assert (db_deploy_dir / "kustomization.yaml").exists()


class TestDeploymentManifest:
    """Test PostgreSQL deployment"""

    def test_uses_postgresql_image(self, db_deploy_dir):
        with open(db_deploy_dir / "deployment.yaml") as f:
            doc = yaml.safe_load(f)
        image = doc['spec']['template']['spec']['containers'][0]['image']
        assert 'postgresql' in image.lower(), "Should use PostgreSQL image"

    def test_has_health_probes(self, db_deploy_dir):
        with open(db_deploy_dir / "deployment.yaml") as f:
            doc = yaml.safe_load(f)
        container = doc['spec']['template']['spec']['containers'][0]
        assert 'livenessProbe' in container, "Should have liveness probe"
        assert 'readinessProbe' in container, "Should have readiness probe"

    def test_mounts_persistent_storage(self, db_deploy_dir):
        with open(db_deploy_dir / "deployment.yaml") as f:
            doc = yaml.safe_load(f)
        container = doc['spec']['template']['spec']['containers'][0]
        mounts = container.get('volumeMounts', [])
        assert len(mounts) > 0, "Should mount persistent storage"


class TestPVC:
    """Test persistent volume claim"""

    def test_pvc_has_sufficient_storage(self, db_deploy_dir):
        with open(db_deploy_dir / "pvc.yaml") as f:
            doc = yaml.safe_load(f)
        storage = doc['spec']['resources']['requests']['storage']
        storage_gi = parse_k8s_memory_gi(storage)
        assert storage_gi >= 10, f"PVC should be at least 10Gi, got {storage}"


class TestNetworkPolicy:
    """Test network policy restricts access"""

    def test_allows_gateway_access(self, db_deploy_dir):
        with open(db_deploy_dir / "network-policy.yaml") as f:
            content = f.read()
        assert 'intel-rh-inference-gateway' in content, \
            "Should allow access from gateway namespace"

    def test_restricts_to_port_5432(self, db_deploy_dir):
        with open(db_deploy_dir / "network-policy.yaml") as f:
            content = f.read()
        assert '5432' in content, "Should restrict to PostgreSQL port 5432"


class TestKustomization:
    """Test kustomization includes all resources"""

    def test_includes_all_resources(self, db_deploy_dir):
        with open(db_deploy_dir / "kustomization.yaml") as f:
            doc = yaml.safe_load(f)
        resources = doc.get('resources', [])
        assert 'namespace.yaml' in resources
        assert 'deployment.yaml' in resources
        assert 'service.yaml' in resources
        assert 'pvc.yaml' in resources
        assert 'secret.yaml' in resources
        assert 'network-policy.yaml' in resources


class TestAnsibleRole:
    """Test database Ansible role"""

    def test_role_exists(self, project_root):
        role_dir = project_root / "ansible" / "roles" / "database" / "tasks"
        assert (role_dir / "main.yaml").exists(), "Database Ansible role not found"

    def test_role_deploys_manifests(self, project_root):
        content = (project_root / "ansible" / "roles" / "database" / "tasks" / "main.yaml").read_text()
        assert 'database' in content, "Role should deploy database manifests"

    def test_role_verifies_readiness(self, project_root):
        content = (project_root / "ansible" / "roles" / "database" / "tasks" / "main.yaml").read_text()
        assert 'pg_isready' in content, "Role should verify PostgreSQL readiness"

    def test_platform_playbook_includes_database(self, project_root):
        content = (project_root / "ansible" / "playbooks" / "deploy-platform.yaml").read_text()
        assert 'database' in content, "deploy-platform.yaml should include database role"
