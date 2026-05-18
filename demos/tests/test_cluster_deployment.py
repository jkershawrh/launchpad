#!/usr/bin/env python3
"""Tests for cluster deployment manifests (deploy/cluster/)."""
import pytest
import yaml
import subprocess
from pathlib import Path


@pytest.fixture
def cluster_dir(project_root):
    return project_root / "deploy" / "cluster"


class TestClusterManifests:
    def test_cluster_dir_exists(self, cluster_dir):
        assert cluster_dir.exists()

    def test_kustomization_exists(self, cluster_dir):
        assert (cluster_dir / "kustomization.yaml").exists()

    def test_has_namespace(self, cluster_dir):
        content = (cluster_dir / "namespace.yaml").read_text()
        assert "intel-rh-demo" in content

    def test_has_gateway_deployment(self, cluster_dir):
        assert (cluster_dir / "gateway-deployment.yaml").exists()
        content = yaml.safe_load((cluster_dir / "gateway-deployment.yaml").read_text())
        assert content["kind"] == "Deployment"
        assert content["metadata"]["name"] == "gateway"

    def test_has_frontend_deployment(self, cluster_dir):
        assert (cluster_dir / "frontend-deployment.yaml").exists()
        content = yaml.safe_load((cluster_dir / "frontend-deployment.yaml").read_text())
        containers = content["spec"]["template"]["spec"]["containers"]
        names = [c["name"] for c in containers]
        assert "oauth-proxy" in names
        assert "frontend" in names

    def test_has_postgres_deployment(self, cluster_dir):
        assert (cluster_dir / "postgres-deployment.yaml").exists()
        content = yaml.safe_load((cluster_dir / "postgres-deployment.yaml").read_text())
        assert content["spec"]["strategy"]["type"] == "Recreate"

    def test_has_services(self, cluster_dir):
        assert (cluster_dir / "services.yaml").exists()
        text = (cluster_dir / "services.yaml").read_text()
        docs = list(yaml.safe_load_all(text))
        assert len(docs) >= 3

    def test_has_route(self, cluster_dir):
        assert (cluster_dir / "route.yaml").exists()
        content = yaml.safe_load((cluster_dir / "route.yaml").read_text())
        assert content["kind"] == "Route"
        assert content["spec"]["tls"]["termination"] == "reencrypt"

    def test_has_configmap(self, cluster_dir):
        assert (cluster_dir / "configmap.yaml").exists()
        content = yaml.safe_load((cluster_dir / "configmap.yaml").read_text())
        assert "config.local.yaml" in content["data"]

    def test_has_secrets_template(self, cluster_dir):
        assert (cluster_dir / "secrets-template.yaml").exists()
        text = (cluster_dir / "secrets-template.yaml").read_text()
        assert "CHANGE-ME" in text

    def test_no_real_secrets_committed(self, cluster_dir):
        text = (cluster_dir / "secrets-template.yaml").read_text()
        assert "sk-" not in text
        assert "CHANGE-ME" in text

    def test_gateway_has_startup_probe(self, cluster_dir):
        content = yaml.safe_load((cluster_dir / "gateway-deployment.yaml").read_text())
        container = content["spec"]["template"]["spec"]["containers"][0]
        assert "startupProbe" in container

    def test_postgres_backup_exists(self, cluster_dir):
        assert (cluster_dir / "postgres-backup.yaml").exists()
        text = (cluster_dir / "postgres-backup.yaml").read_text()
        assert "CronJob" in text

    def test_oauth_proxy_serviceaccount(self, cluster_dir):
        assert (cluster_dir / "oauth-proxy.yaml").exists()
        content = yaml.safe_load((cluster_dir / "oauth-proxy.yaml").read_text())
        assert content["kind"] == "ServiceAccount"
        assert "oauth-redirectreference" in str(content.get("metadata", {}).get("annotations", {}))
