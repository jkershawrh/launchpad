import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy/launchpad/overlays/flightpath-authentik-canary"


def _render() -> list[dict]:
    rendered = subprocess.run(
        ["oc", "kustomize", str(OVERLAY)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [item for item in yaml.safe_load_all(rendered) if item]


def _one(items: list[dict], kind: str, name: str) -> dict:
    matches = [
        item
        for item in items
        if item.get("kind") == kind and item.get("metadata", {}).get("name") == name
    ]
    assert len(matches) == 1, (kind, name, len(matches))
    return matches[0]


def test_authentik_canary_is_additive_and_keeps_stable_routes():
    items = _render()

    _one(items, "Route", "launchpad")
    _one(items, "Route", "launchpad-admin")
    _one(items, "Route", "launchpad-requester-authentik-canary")
    _one(items, "Route", "launchpad-admin-authentik-canary")


def test_authentik_canary_uses_signed_token_contract_and_pinned_proxy():
    items = _render()
    config = _one(items, "ConfigMap", "launchpad-config")["data"]
    assert config["OIDC_ISSUER"].startswith("https://auth.smg-helix.ai/")
    assert config["OIDC_JWKS_URL"].startswith("https://auth.smg-helix.ai/")
    assert config["OIDC_AUDIENCES"] == "launchpad-workforce"
    assert set(config["OIDC_JWT_HOSTS"].split(",")) == {
        "launchpad-auth-candidate.apps.flightpath.fm2aihpcsed.com",
        "launchpad-admin-auth-candidate.apps.flightpath.fm2aihpcsed.com",
    }

    for name in (
        "launchpad-requester-authentik-canary",
        "launchpad-admin-authentik-canary",
    ):
        deployment = _one(items, "Deployment", name)
        pod_spec = deployment["spec"]["template"]["spec"]
        assert pod_spec["automountServiceAccountToken"] is False
        container = pod_spec["containers"][0]
        assert "@sha256:" in container["image"]
        assert "--set-authorization-header=true" in container["args"]
        assert "--pass-authorization-header=true" in container["args"]
        env = {entry["name"]: entry for entry in container["env"]}
        assert "value" not in env["OAUTH2_PROXY_CLIENT_SECRET"]
        assert "value" not in env["OAUTH2_PROXY_COOKIE_SECRET"]


def test_admin_canary_requires_admin_group_and_no_secret_is_rendered():
    items = _render()
    requester = _one(items, "Deployment", "launchpad-requester-authentik-canary")
    requester_args = requester["spec"]["template"]["spec"]["containers"][0]["args"]
    assert "--allowed-group=launchpad-requesters" in requester_args

    deployment = _one(items, "Deployment", "launchpad-admin-authentik-canary")
    args = deployment["spec"]["template"]["spec"]["containers"][0]["args"]
    assert "--allowed-group=launchpad-admins" in args
    assert not any(item.get("kind") == "Secret" for item in items)


def test_canary_ingress_is_limited_to_openshift_router():
    items = _render()
    policy = _one(items, "NetworkPolicy", "authentik-workforce-canary-ingress")
    ingress = policy["spec"]["ingress"]
    assert ingress[0]["from"][0]["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": "openshift-ingress"
    }
