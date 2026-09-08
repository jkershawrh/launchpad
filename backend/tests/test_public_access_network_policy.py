"""Network-policy contract for participant ingress paths."""

from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
ARENA_OVERLAY = ROOT / "deploy/launchpad/overlays/arena"


def test_public_gateway_accepts_the_managed_cloudflare_tunnel():
    rendered = subprocess.run(
        ["oc", "kustomize", str(ARENA_OVERLAY)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    policies = list(yaml.safe_load_all(rendered))
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
