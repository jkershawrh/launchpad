"""TDD tests for NetworkPolicy in demo namespaces — Phase 6 gate matrix."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _build_network_policy():
    """Build the NetworkPolicy dict and validate its structure."""
    from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter

    policy = OpenShiftProvisioningAdapter._build_demo_network_policy("test-ns")
    return policy


# ── Gate 6.1: test_demo_namespace_gets_network_policy ────────────────

class TestDemoNamespaceGetsNetworkPolicy:
    def test_builds_valid_network_policy(self):
        policy = _build_network_policy()
        assert policy["kind"] == "NetworkPolicy"
        assert policy["apiVersion"] == "networking.k8s.io/v1"
        assert policy["metadata"]["name"] == "demo-egress-restrict"
        assert policy["metadata"]["namespace"] == "test-ns"


# ── Gate 6.2: test_network_policy_allows_litellm ────────────────────

class TestNetworkPolicyAllowsLiteLLM:
    def test_allows_intel_inference_egress(self):
        policy = _build_network_policy()
        egress = policy["spec"]["egress"]

        ns_rules = [
            r for r in egress
            if any(
                ns.get("namespaceSelector", {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == "intel-inference"
                for to in r.get("to", [])
                for ns in ([to] if "namespaceSelector" in to else [])
            )
        ]
        assert len(ns_rules) >= 1


# ── Gate 6.3: test_network_policy_allows_dns ─────────────────────────

class TestNetworkPolicyAllowsDns:
    def test_allows_dns_port_53(self):
        policy = _build_network_policy()
        egress = policy["spec"]["egress"]

        dns_rules = [
            r for r in egress
            if any(
                p.get("port") == 53
                for p in r.get("ports", [])
            )
        ]
        assert len(dns_rules) >= 1


# ── Gate 6.4: test_network_policy_denies_other_egress ────────────────

class TestNetworkPolicyDeniesOtherEgress:
    def test_policy_type_includes_egress(self):
        policy = _build_network_policy()
        assert "Egress" in policy["spec"]["policyTypes"]

    def test_has_pod_selector(self):
        policy = _build_network_policy()
        assert policy["spec"]["podSelector"] == {}


# ── Gate 6.C1: NetworkPolicy K8s spec ────────────────────────────────

class TestNetworkPolicySpec:
    def test_valid_api_version(self):
        policy = _build_network_policy()
        assert policy["apiVersion"] == "networking.k8s.io/v1"

    def test_valid_kind(self):
        policy = _build_network_policy()
        assert policy["kind"] == "NetworkPolicy"

    def test_has_spec(self):
        policy = _build_network_policy()
        assert "spec" in policy
        assert "podSelector" in policy["spec"]
        assert "policyTypes" in policy["spec"]
        assert "egress" in policy["spec"]
