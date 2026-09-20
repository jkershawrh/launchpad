from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "deploy" / "launchpad" / "catalog-intake-cert"


def _documents(name: str) -> list[dict]:
    return [item for item in yaml.safe_load_all((BASE / name).read_text()) if item]


def test_certification_namespace_is_explicitly_nonproduction() -> None:
    namespace = _documents("namespace.yaml")[0]
    assert namespace["metadata"]["name"] == "launchpad-catalog-intake-cert"
    labels = namespace["metadata"]["labels"]
    assert labels["launchpad.redhat.com/live-catalog-access"] == "false"
    assert labels["launchpad.redhat.com/workshop-access"] == "false"


def test_proxy_has_no_token_or_secret_and_is_restricted() -> None:
    deployment = _documents("proxy.yaml")[0]
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert pod["automountServiceAccountToken"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert "secret" not in str(container).lower()
    assert container["env"][0]["value"] == "github.com,api.github.com"


def test_binary_build_is_separate_from_runtime_identity() -> None:
    resources = {(item["kind"], item["metadata"]["name"]): item for item in _documents("build.yaml")}
    build = resources[("BuildConfig", "catalog-intake-worker")]["spec"]
    assert build["source"] == {"type": "Binary", "binary": {}}
    assert build["strategy"]["dockerStrategy"]["dockerfilePath"] == (
        "backend/Containerfile.catalog-intake-worker"
    )
    assert build["triggers"] == []
    assert "nodeSelector" not in build


def test_network_policy_defaults_to_deny_and_blocks_private_egress() -> None:
    policies = {item["metadata"]["name"]: item for item in _documents("network-policy.yaml")}
    assert policies["default-deny"]["spec"] == {
        "podSelector": {
            "matchExpressions": [
                {
                    "key": "app.kubernetes.io/name",
                    "operator": "In",
                    "values": [
                        "catalog-intake-worker",
                        "catalog-intake-egress-proxy",
                    ],
                }
            ]
        },
        "policyTypes": ["Ingress", "Egress"],
    }
    rules = policies["egress-proxy-egress"]["spec"]["egress"]
    assert rules[0]["to"] == [
        {
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": "openshift-dns"}
            }
        }
    ]
    internet = rules[1]["to"][0]["ipBlock"]
    assert internet["cidr"] == "0.0.0.0/0"
    assert "10.0.0.0/8" in internet["except"]
    assert "172.16.0.0/12" in internet["except"]
    assert rules[1]["ports"] == [{"protocol": "TCP", "port": 443}]
