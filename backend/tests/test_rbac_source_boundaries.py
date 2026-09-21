"""Non-live guardrails for the checked-in Launchpad RBAC manifests."""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _documents(path: str) -> list[dict]:
    return [
        item
        for item in yaml.safe_load_all((ROOT / path).read_text())
        if isinstance(item, dict)
    ]


def _render_arena() -> list[dict]:
    output = subprocess.check_output(
        ["oc", "kustomize", "deploy/launchpad/overlays/arena"],
        cwd=ROOT,
        text=True,
    )
    return [item for item in yaml.safe_load_all(output) if isinstance(item, dict)]


def test_provisioner_roles_have_no_wildcard_or_cluster_admin_grant() -> None:
    sources = (
        _render_arena(),
        _documents("deploy/multicluster/arena-rbac.yaml"),
        _documents("deploy/multicluster/flightpath-remote-rbac.yaml"),
    )

    for documents in sources:
        for item in documents:
            if item.get("kind") == "ClusterRoleBinding":
                assert item["roleRef"]["name"] != "cluster-admin"
            if item.get("kind") != "ClusterRole":
                continue
            for rule in item["rules"]:
                assert "*" not in rule.get("resources", [])
                assert "*" not in rule.get("verbs", [])


def test_arena_render_does_not_emit_placeholder_secret_objects() -> None:
    arena = _render_arena()

    assert not [item for item in arena if item.get("kind") == "Secret"]
