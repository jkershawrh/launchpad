from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_candidate_can_only_remove_stale_pipelines_subjects() -> None:
    rendered = subprocess.run(
        ["oc", "kustomize", "deploy/launchpad/overlays/flightpath-candidate"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    documents = [item for item in yaml.safe_load_all(rendered) if item]
    candidate_role = next(
        item
        for item in documents
        if item.get("kind") == "ClusterRole"
        and item["metadata"]["name"] == "launchpad-flightpath-candidate-provisioner"
    )

    assert any(
        rule["resources"] == ["clusterroles"]
        and "openshift-pipelines-clusterinterceptors" in rule["resourceNames"]
        and rule["verbs"] == ["bind"]
        for rule in candidate_role["rules"]
    )
    assert any(
        rule["resources"] == ["clusterrolebindings"]
        and rule["resourceNames"] == ["openshift-pipelines-clusterinterceptors"]
        and set(rule["verbs"]) == {"get", "update", "patch"}
        for rule in candidate_role["rules"]
    )

    boundary = next(
        item
        for item in documents
        if item.get("kind") == "ValidatingAdmissionPolicy"
        and item["metadata"]["name"]
        == "launchpad-flightpath-candidate-namespace-boundary"
    )
    expression = boundary["spec"]["validations"][0]["expression"]
    assert "object.subjects.all" in expression
    assert "subject.namespace.startsWith('launchpad-')" in expression
