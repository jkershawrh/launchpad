#!/usr/bin/env python3
"""Tenant Onboarding Infrastructure — structural tests."""

import pytest
from pathlib import Path


# ─── Ansible Role Structure ───

class TestTenantOnboardRole:

    def test_role_exists(self, project_root):
        assert (project_root / "ansible" / "roles" / "tenant_onboard" / "tasks" / "main.yaml").exists()

    def test_has_templates(self, project_root):
        templates = project_root / "ansible" / "roles" / "tenant_onboard" / "templates"
        assert templates.exists()
        assert (templates / "resource-quota.yaml.j2").exists()
        assert (templates / "limit-range.yaml.j2").exists()
        assert (templates / "network-policy.yaml.j2").exists()

    def test_tasks_create_namespace(self, project_root):
        tasks = (project_root / "ansible" / "roles" / "tenant_onboard" / "tasks" / "main.yaml").read_text()
        assert "namespace" in tasks.lower()
        assert "tenant_slug" in tasks

    def test_tasks_apply_network_policy(self, project_root):
        tasks = (project_root / "ansible" / "roles" / "tenant_onboard" / "tasks" / "main.yaml").read_text()
        assert "network" in tasks.lower()

    def test_tasks_apply_resource_quota(self, project_root):
        tasks = (project_root / "ansible" / "roles" / "tenant_onboard" / "tasks" / "main.yaml").read_text()
        assert "quota" in tasks.lower()

    def test_network_policy_restricts_ingress(self, project_root):
        netpol = (project_root / "ansible" / "roles" / "tenant_onboard" / "templates" / "network-policy.yaml.j2").read_text()
        assert "intel-rh-inference-gateway" in netpol
        assert "Ingress" in netpol

    def test_network_policy_restricts_egress(self, project_root):
        netpol = (project_root / "ansible" / "roles" / "tenant_onboard" / "templates" / "network-policy.yaml.j2").read_text()
        assert "intel-rh-cpu-inference" in netpol
        assert "intel-rh-gaudi-inference" in netpol
        assert "Egress" in netpol


# ─── Playbook ───

class TestOnboardPlaybook:

    def test_playbook_exists(self, project_root):
        assert (project_root / "ansible" / "playbooks" / "onboard-partner.yaml").exists()

    def test_playbook_uses_role(self, project_root):
        pb = (project_root / "ansible" / "playbooks" / "onboard-partner.yaml").read_text()
        assert "tenant_onboard" in pb

    def test_playbook_has_required_vars(self, project_root):
        pb = (project_root / "ansible" / "playbooks" / "onboard-partner.yaml").read_text()
        assert "tenant_slug" in pb
        assert "tenant_tier" in pb


# ─── Kustomize Tenant Base ───

class TestKustomizeTenantBase:

    def test_base_exists(self, project_root):
        assert (project_root / "deploy" / "tenants" / "base" / "kustomization.yaml").exists()

    def test_has_namespace(self, project_root):
        assert (project_root / "deploy" / "tenants" / "base" / "namespace.yaml").exists()

    def test_has_network_policy(self, project_root):
        assert (project_root / "deploy" / "tenants" / "base" / "network-policy.yaml").exists()

    def test_has_resource_quota(self, project_root):
        assert (project_root / "deploy" / "tenants" / "base" / "resource-quota.yaml").exists()

    def test_has_limit_range(self, project_root):
        assert (project_root / "deploy" / "tenants" / "base" / "limit-range.yaml").exists()

    def test_network_policy_isolates_tenants(self, project_root):
        netpol = (project_root / "deploy" / "tenants" / "base" / "network-policy.yaml").read_text()
        assert "intel-rh-inference-gateway" in netpol
        assert "Ingress" in netpol
        assert "Egress" in netpol
