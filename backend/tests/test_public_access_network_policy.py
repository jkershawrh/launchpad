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


def test_arena_public_gateway_validates_the_stable_keycloak_issuer():
    rendered = subprocess.run(
        ["oc", "kustomize", str(ARENA_OVERLAY)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    resources = list(yaml.safe_load_all(rendered))
    deployment = next(
        item
        for item in resources
        if item.get("kind") == "Deployment"
        and item["metadata"]["name"] == "public-access-gateway"
    )
    proxy = next(
        container
        for container in deployment["spec"]["template"]["spec"]["containers"]
        if container["name"] == "oidc-proxy"
    )
    env = {item["name"]: item.get("value") for item in proxy["env"]}

    assert env["OAUTH2_PROXY_OIDC_ISSUER_URL"] == (
        "https://keycloak.apps.arena.fm2aihpcsed.com/realms/launchpad-public"
    )


def test_arena_gateway_verifies_internal_ingress_with_the_cluster_ca_bundle():
    rendered = subprocess.run(
        ["oc", "kustomize", str(ARENA_OVERLAY)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    resources = list(yaml.safe_load_all(rendered))
    deployment = next(
        item
        for item in resources
        if item.get("kind") == "Deployment"
        and item["metadata"]["name"] == "public-access-gateway"
    )
    gateway = next(
        container
        for container in deployment["spec"]["template"]["spec"]["containers"]
        if container["name"] == "gateway"
    )
    env = {item["name"]: item.get("value") for item in gateway["env"]}
    mounts = {item["name"]: item for item in gateway["volumeMounts"]}
    volumes = {
        item["name"]: item
        for item in deployment["spec"]["template"]["spec"]["volumes"]
    }

    assert env["PUBLIC_UPSTREAM_TLS_VERIFY"] == "true"
    assert env["SSL_CERT_FILE"] == "/etc/launchpad-ca/ca-bundle.crt"
    assert env["REQUESTS_CA_BUNDLE"] == "/etc/launchpad-ca/ca-bundle.crt"
    assert mounts["cluster-ca-bundle"]["mountPath"] == "/etc/launchpad-ca"
    assert volumes["cluster-ca-bundle"]["configMap"] == {
        "name": "launchpad-cluster-ca-bundle",
        "optional": False,
    }
