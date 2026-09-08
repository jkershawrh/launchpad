import importlib.util
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _router_module():
    path = ROOT / "deploy/tunnel-oncluster/router.py"
    spec = importlib.util.spec_from_file_location("launchpad_tunnel_router", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_on_cluster_tunnel_has_a_dedicated_unprivileged_identity():
    manifest = (ROOT / "deploy/tunnel-oncluster/deployment.yaml").read_text()

    assert "kind: ServiceAccount" in manifest
    assert "name: launchpad-public-tunnel" in manifest
    assert "serviceAccountName: launchpad-public-tunnel" in manifest
    assert "ClusterRoleBinding" not in manifest
    assert "cluster-admin" not in manifest
    assert "serviceAccountName: launchpad-backend" not in manifest


def test_tunnel_manifest_cannot_overwrite_rendered_router_or_require_a_shell():
    manifest = (ROOT / "deploy/tunnel-oncluster/deployment.yaml").read_text()

    assert "kind: ConfigMap" not in manifest
    assert "Replaced from deploy/tunnel-oncluster/router.py" not in manifest
    assert "args: [tunnel, --url, http://127.0.0.1:8080, --no-autoupdate]" in manifest
    assert "command: [/bin/sh" not in manifest
    assert "tee /shared/cloudflared.log" not in manifest


def test_tunnel_does_not_take_ownership_of_managed_console_or_authentication():
    scripts = "\n".join(
        (ROOT / path).read_text()
        for path in (
            "deploy/tunnel-oncluster/apply.sh",
            "deploy/tunnel-oncluster/propagate.sh",
            "scripts/start-tunnel.sh",
            "scripts/stop-tunnel.sh",
        )
    )

    assert "scale deployment console-operator" not in scripts
    assert "patch oauthclient console" not in scripts
    assert "OAUTH2_PROXY_INSECURE_OIDC_SKIP_ISSUER_VERIFICATION=true" not in scripts
    assert "/rotate" not in scripts
    assert "UPDATE access_policies" not in scripts


def test_console_proxy_preserves_http_only_oauth_cookies():
    router = (ROOT / "deploy/tunnel-oncluster/router.py").read_text()

    assert "document.cookie" not in router
    assert "_login_state_cache" not in router
    assert "set-cookie" in router


def test_tunnel_scripts_pin_every_cluster_call_to_arena_kubeconfig():
    for path in (
        "deploy/tunnel-oncluster/apply.sh",
        "scripts/start-tunnel.sh",
        "scripts/stop-tunnel.sh",
    ):
        script = (ROOT / path).read_text()
        assert "/Users/jkershaw/.kube/config-arena" in script
        assert "export KUBECONFIG" in script


def test_pilot_can_start_before_an_order_and_configures_only_arena_public_placement():
    script = (ROOT / "deploy/tunnel-oncluster/apply.sh").read_text()

    assert '[[ -n "$ORDER_ID" ]] || die' not in script
    assert 'PUBLIC_LABS_SHARED_ORIGIN=$tunnel_url' in script
    assert 'PUBLIC_ACCESS_PILOT_CLUSTER=arena' in script
    assert "scale deployment/public-access-gateway --replicas=1" in script
    assert 'if [[ -n "$ORDER_ID" ]]' in script


def test_stopping_the_disposable_pilot_fails_public_ordering_closed():
    script = (ROOT / "scripts/stop-tunnel.sh").read_text()

    assert "PUBLIC_ACCESS_ENABLED-" in script
    assert "PUBLIC_LABS_SHARED_ORIGIN-" in script
    assert "PUBLIC_ACCESS_PILOT_CLUSTER-" in script
    assert "scale deployment/public-access-gateway --replicas=0" in script
    assert "rollout status deployment/backend" in script


def test_console_router_rewrites_origins_but_preserves_encoded_redirect_uri():
    router = _router_module()
    tunnel_host = "pilot.trycloudflare.com"
    encoded_callback = (
        "https%3A%2F%2Fconsole-openshift-console.apps.arena.fm2aihpcsed.com"
        "%2Fauth%2Fcallback"
    )
    source = (
        "https://oauth-openshift.apps.arena.fm2aihpcsed.com/oauth/authorize"
        f"?redirect_uri={encoded_callback}"
    )

    rewritten = router._rewrite_url(source, tunnel_host)

    assert rewritten.startswith(f"https://{tunnel_host}/oauth/authorize")
    assert encoded_callback in rewritten


def test_console_router_uses_root_spa_paths_after_oauth_callback():
    router = _router_module()
    tunnel_host = "pilot.trycloudflare.com"

    rewritten = router._rewrite_url(
        "https://console-openshift-console.apps.arena.fm2aihpcsed.com"
        "/console/topology/ns/participant-seat",
        tunnel_host,
    )

    assert rewritten == (
        f"https://{tunnel_host}/k8s/ns/participant-seat/core~v1~Pod"
    )
    assert router._canonical_public_path(
        "console/console/topology/ns/participant-seat"
    ) == "k8s/ns/participant-seat/core~v1~Pod"
    assert router._select_upstream("k8s/ns/participant-seat/core~v1~Pod") == (
        router.CONSOLE_ORIGIN,
        "k8s/ns/participant-seat/core~v1~Pod",
        True,
    )
    assert router._rewrite_console_body(b'<base href="/"/>', tunnel_host) == (
        b'<base href="/"/>'
    )


def test_console_url_rewrite_preserves_valid_showroom_yaml():
    router = _router_module()
    tunnel_host = "pilot.trycloudflare.com"
    source = (
        "type: showroom\n"
        "tabs:\n"
        "  - name: OpenShift Console\n"
        "    url: https://console-openshift-console.apps.arena.fm2aihpcsed.com"
        "/topology/ns/participant-seat\n"
    )

    rewritten = router._rewrite_url(source, tunnel_host)
    parsed = yaml.safe_load(rewritten)

    assert parsed["tabs"][0]["url"] == (
        f"https://{tunnel_host}/k8s/ns/participant-seat/core~v1~Pod"
    )
    assert "\n/core~v1~Pod" not in rewritten


def test_console_url_rewrite_preserves_json_boundaries():
    router = _router_module()
    tunnel_host = "pilot.trycloudflare.com"
    source = json.dumps({
        "items": [{
            "metadata": {
                "annotations": {
                    "console_url": (
                        "https://console-openshift-console.apps.arena.fm2aihpcsed.com"
                        "/topology/ns/participant-seat"
                    ),
                    "status": "ready",
                }
            }
        }]
    })

    rewritten = router._rewrite_url(source, tunnel_host)
    parsed = json.loads(rewritten)

    assert parsed["items"][0]["metadata"]["annotations"]["console_url"] == (
        f"https://{tunnel_host}/k8s/ns/participant-seat/core~v1~Pod"
    )
    assert parsed["items"][0]["metadata"]["annotations"]["status"] == "ready"


def test_console_router_keeps_http_only_and_scopes_proxy_cookie_paths():
    router = _router_module()

    console_cookie = router._fix_cookie_samesite(
        "openshift-session-token=secret; Path=/; HttpOnly; Secure; SameSite=Lax",
        path_prefix="console/",
    )
    oauth_cookie = router._fix_cookie_samesite(
        "ssn=secret; Path=/; HttpOnly; Secure",
        path_prefix="oauth/",
    )

    assert "HttpOnly" in console_cookie
    assert "Path=/;" in console_cookie
    assert "SameSite=None" in console_cookie
    assert "HttpOnly" in oauth_cookie
    assert "Path=/oauth" in oauth_cookie
