"""Network-policy contract for participant ingress paths."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
NETWORK_POLICY = ROOT / "deploy/launchpad/base/network-policy.yaml"


def test_public_gateway_accepts_the_managed_cloudflare_tunnel():
    policies = list(yaml.safe_load_all(NETWORK_POLICY.read_text()))
    policy = next(
        item
        for item in policies
        if item["metadata"]["name"] == "public-access-gateway-ingress"
    )

    sources = policy["spec"]["ingress"][0]["from"]
    assert {
        "podSelector": {
            "matchLabels": {"app.kubernetes.io/name": "cloudflare-tunnel"}
        }
    } in sources
