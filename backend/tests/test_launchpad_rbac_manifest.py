from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_provisioner_can_bind_only_the_edit_cluster_role():
    documents = list(yaml.safe_load_all(
        (ROOT / "deploy/launchpad/base/rbac.yaml").read_text()
    ))
    provisioner = next(
        document for document in documents
        if document.get("kind") == "ClusterRole"
        and document["metadata"]["name"] == "launchpad-provisioner"
    )
    bind_rules = [
        rule for rule in provisioner["rules"]
        if "bind" in rule.get("verbs", [])
    ]

    assert bind_rules == [{
        "apiGroups": ["rbac.authorization.k8s.io"],
        "resources": ["clusterroles"],
        "resourceNames": ["edit"],
        "verbs": ["bind"],
    }]
