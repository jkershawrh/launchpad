"""Local contract for the proposed remote provisioner privilege boundary.

Flightpath is a design reference, not evidence that Arena or Brutus has been
migrated. These checks never contact or change a cluster.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "deploy/multicluster/flightpath-remote-rbac.yaml"
PROVISIONER = "launchpad-provisioner-flightpath"
ARGOCD = "launchpad-argocd-manager-flightpath"
NAMESPACE = "partner-ai-launchpad"


def _resources() -> list[dict]:
    return [item for item in yaml.safe_load_all(MANIFEST.read_text()) if item]


def _named(items: list[dict], kind: str, name: str) -> dict:
    return next(
        item
        for item in items
        if item["kind"] == kind and item["metadata"]["name"] == name
    )


def test_remote_global_bindings_exclude_seat_manager_and_workload_writes() -> None:
    items = _resources()
    roles = {
        item["metadata"]["name"]: item
        for item in items
        if item["kind"] == "ClusterRole"
    }
    bindings = [item for item in items if item["kind"] == "ClusterRoleBinding"]

    assert {item["roleRef"]["name"] for item in bindings} == {
        "launchpad-flightpath-provisioner-bootstrap",
        "launchpad-flightpath-argocd-discovery",
    }
    assert {
        (item["subjects"][0]["name"], item["roleRef"]["name"])
        for item in bindings
    } == {
        (PROVISIONER, "launchpad-flightpath-provisioner-bootstrap"),
        (ARGOCD, "launchpad-flightpath-argocd-discovery"),
    }
    for binding in bindings:
        assert binding["subjects"] == [
            {
                "kind": "ServiceAccount",
                "name": binding["subjects"][0]["name"],
                "namespace": NAMESPACE,
            }
        ]
        for rule in roles[binding["roleRef"]["name"]]["rules"]:
            assert "*" not in rule.get("resources", [])
            assert "*" not in rule.get("verbs", [])
            if set(rule.get("verbs", [])) & {
                "create", "update", "patch", "delete", "deletecollection"
            }:
                assert set(rule.get("resources", [])) <= {
                    "namespaces", "rolebindings", "selfsubjectaccessreviews"
                }


def test_seat_manager_permissions_require_namespaced_binding() -> None:
    items = _resources()
    cluster_bound = {
        item["roleRef"]["name"]
        for item in items
        if item["kind"] == "ClusterRoleBinding"
    }
    for name in (
        "launchpad-flightpath-seat-manager",
        "launchpad-flightpath-argocd-seat-manager",
    ):
        role = _named(items, "ClusterRole", name)
        assert name not in cluster_bound
        assert any("secrets" in rule.get("resources", []) for rule in role["rules"])
        assert all("*" not in rule.get("resources", []) for rule in role["rules"])
        assert all("*" not in rule.get("verbs", []) for rule in role["rules"])


def test_bootstrap_binding_is_constrained_by_fail_closed_admission() -> None:
    items = _resources()
    policy = _named(
        items, "ValidatingAdmissionPolicy", "launchpad-flightpath-namespace-boundary"
    )
    binding = _named(
        items, "ValidatingAdmissionPolicyBinding", "launchpad-flightpath-namespace-boundary"
    )
    assert policy["spec"]["failurePolicy"] == "Fail"
    assert binding["spec"]["policyName"] == policy["metadata"]["name"]
    assert binding["spec"]["validationActions"] == ["Deny"]
    assert policy["spec"]["matchConstraints"]["resourceRules"][0]["operations"] == [
        "CREATE", "UPDATE", "DELETE"
    ]
    expression = policy["spec"]["validations"][0]["expression"]
    assert f"system:serviceaccount:{NAMESPACE}:{PROVISIONER}" in expression
    assert "request.namespace.startsWith('launchpad-')" in expression
    assert "oldObject.metadata.name" in expression
    assert "object.metadata.name" in expression
