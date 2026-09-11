import importlib.util
import json
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
ARENA_OVERLAY = ROOT / "deploy/launchpad/overlays/arena"
PUBLIC_ORIGIN = "https://labs.smg-helix.ai"


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


def test_named_tunnel_has_checked_in_kustomize_source_for_the_router_config():
    kustomization = (ROOT / "deploy/tunnel-oncluster/kustomization.yaml").read_text()
    rendered = subprocess.run(
        ["oc", "kustomize", str(ROOT / "deploy/tunnel-oncluster")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    resources = list(yaml.safe_load_all(rendered))

    assert "deployment.yaml" in kustomization
    assert "configMapGenerator:" in kustomization
    assert "name: tunnel-router" in kustomization
    assert "router.py" in kustomization
    assert "disableNameSuffixHash: true" in kustomization
    assert all(
        item["metadata"]["labels"]["app.kubernetes.io/managed-by"] == "kustomize"
        for item in resources
    )


def test_named_tunnel_uses_the_precreated_token_without_a_shell():
    manifest = (ROOT / "deploy/tunnel-oncluster/deployment.yaml").read_text()

    assert "kind: ConfigMap" not in manifest
    assert "Replaced from deploy/tunnel-oncluster/router.py" not in manifest
    assert "args: [tunnel, --no-autoupdate, --loglevel, info, --metrics, 0.0.0.0:2000, run]" in manifest
    assert "name: TUNNEL_TOKEN" in manifest
    assert "secretKeyRef: {name: tunnel-token, key: token}" in manifest
    assert "--url" not in manifest
    assert "command: [/bin/sh" not in manifest
    assert "tee /shared/cloudflared.log" not in manifest


def test_named_tunnel_has_two_connection_aware_replicas_and_a_disruption_budget():
    rendered = subprocess.run(
        ["oc", "kustomize", str(ROOT / "deploy/tunnel-oncluster")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    resources = list(yaml.safe_load_all(rendered))
    deployment = next(
        item
        for item in resources
        if item.get("kind") == "Deployment"
        and item["metadata"]["name"] == "cloudflare-tunnel"
    )
    disruption_budget = next(
        item
        for item in resources
        if item.get("kind") == "PodDisruptionBudget"
        and item["metadata"]["name"] == "cloudflare-tunnel"
    )
    spec = deployment["spec"]
    pod_spec = spec["template"]["spec"]
    cloudflared = next(
        item for item in pod_spec["containers"] if item["name"] == "cloudflared"
    )

    assert spec["replicas"] == 2
    assert spec["strategy"] == {
        "type": "RollingUpdate",
        "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 1},
    }
    assert cloudflared["args"] == [
        "tunnel",
        "--no-autoupdate",
        "--loglevel",
        "info",
        "--metrics",
        "0.0.0.0:2000",
        "run",
    ]
    assert {port["name"]: port["containerPort"] for port in cloudflared["ports"]}[
        "metrics"
    ] == 2000
    assert cloudflared["readinessProbe"]["httpGet"] == {
        "path": "/ready",
        "port": "metrics",
    }
    assert cloudflared["livenessProbe"]["httpGet"] == {
        "path": "/ready",
        "port": "metrics",
    }
    required = pod_spec["affinity"]["podAntiAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"
    ]
    assert required[0]["topologyKey"] == "kubernetes.io/hostname"
    assert "nodeSelector" not in pod_spec
    assert disruption_budget["spec"]["minAvailable"] == 1
    assert disruption_budget["spec"]["selector"]["matchLabels"] == {
        "app.kubernetes.io/name": "cloudflare-tunnel"
    }


def test_arena_reliability_alerts_on_tunnel_connector_degradation_and_loss():
    resources = list(yaml.safe_load_all(
        (ARENA_OVERLAY / "reliability.yaml").read_text()
    ))
    rule = next(item for item in resources if item.get("kind") == "PrometheusRule")
    alerts = {
        item["alert"]: item
        for group in rule["spec"]["groups"]
        for item in group["rules"]
        if "alert" in item
    }

    degraded = alerts["CloudflareTunnelReplicaDegraded"]
    unavailable = alerts["CloudflareTunnelUnavailable"]
    assert 'deployment="cloudflare-tunnel"' in degraded["expr"]
    assert "< 2" in degraded["expr"]
    assert degraded["labels"]["severity"] == "warning"
    assert 'deployment="cloudflare-tunnel"' in unavailable["expr"]
    assert "< 1" in unavailable["expr"]
    assert unavailable["labels"]["severity"] == "critical"


def test_public_validation_matrix_does_not_overstate_scale_or_worker_ha():
    matrix = yaml.safe_load(
        (ROOT / "evidence/public-access/validation-matrix-v7.yaml").read_text()
    )
    rows = {item["id"]: item for item in matrix["rows"]}

    assert matrix["version"] == 7
    assert rows["PA-DNS-001"]["stage"] == "GREEN-live"
    assert rows["PA-TUNNEL-022"]["stage"] == "GREEN-live"
    assert rows["PA-CONC-005"]["stage"] == "RED"
    assert rows["PA-LIVE25-016"]["stage"] == "RED"
    assert rows["PA-CONSOLE-009"]["stage"] == "RED"
    assert rows["PA-NODEHA-023"]["stage"] == "RED"
    assert rows["PA-WSFAIL-024"]["stage"] == "RED"
    assert (
        "evidence/runs/public-tunnel-connector-failover-green-live-20260909.json"
        in rows["PA-TUNNEL-022"]["evidence"]
    )


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
    assert f'PUBLIC_ORIGIN="${{PUBLIC_ORIGIN:-{PUBLIC_ORIGIN}}}"' in script
    assert 'PUBLIC_LABS_DOMAIN=$public_host' in script
    assert 'PUBLIC_LABS_SHARED_ORIGIN=$PUBLIC_ORIGIN' in script
    assert 'PUBLIC_LABS_SHARED_PATH_MODE=true' in script
    assert 'PUBLIC_ACCESS_PILOT_CLUSTER=arena' in script
    assert "for deployment in backend lifecycle-worker" in script
    assert 'oc set env deployment/"$deployment"' in script
    assert 'cluster["public_ingress_domain"] = os.environ["PUBLIC_HOST"]' in script
    assert "configmap launchpad-cluster-targets" in script
    assert "scale deployment/public-access-gateway --replicas=1" in script
    assert 'if [[ -n "$ORDER_ID" ]]' in script
    assert "trycloudflare.com" not in script


def test_stopping_the_named_tunnel_fails_public_ordering_closed():
    script = (ROOT / "scripts/stop-tunnel.sh").read_text()

    assert "PUBLIC_ACCESS_ENABLED=false" in script
    assert "PUBLIC_LABS_SHARED_ORIGIN=" in script
    assert "PUBLIC_ACCESS_PILOT_CLUSTER=" in script
    assert "PUBLIC_LABS_SHARED_PATH_MODE=false" in script
    assert "oc set env deployment/lifecycle-worker" in script
    assert 'cluster["public_console_url"] = ""' in script
    assert 'cluster["public_oauth_url"] = ""' in script
    assert "scale deployment/public-access-gateway --replicas=0" in script
    assert "rollout status deployment/backend" in script


def test_arena_overlay_persists_the_named_public_origin_and_strict_oidc_contract():
    rendered = subprocess.run(
        ["oc", "kustomize", str(ARENA_OVERLAY)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    resources = list(yaml.safe_load_all(rendered))
    config = next(
        item
        for item in resources
        if item.get("kind") == "ConfigMap"
        and item["metadata"]["name"] == "launchpad-config"
    )["data"]
    clusters = yaml.safe_load(next(
        item
        for item in resources
        if item.get("kind") == "ConfigMap"
        and item["metadata"]["name"] == "launchpad-cluster-targets"
    )["data"]["clusters.yaml"])["clusters"]
    arena = next(item for item in clusters if item["cluster_id"] == "arena")
    gateway = next(
        item
        for item in resources
        if item.get("kind") == "Deployment"
        and item["metadata"]["name"] == "public-access-gateway"
    )
    proxy = next(
        item
        for item in gateway["spec"]["template"]["spec"]["containers"]
        if item["name"] == "oidc-proxy"
    )
    env = {item["name"]: item.get("value") for item in proxy["env"]}

    assert config["PUBLIC_ACCESS_ENABLED"] == "true"
    assert config["PUBLIC_LABS_DOMAIN"] == "labs.smg-helix.ai"
    assert config["PUBLIC_LABS_SHARED_ORIGIN"] == PUBLIC_ORIGIN
    assert config["PUBLIC_LABS_SHARED_PATH_MODE"] == "true"
    assert config["PUBLIC_ACCESS_PILOT_CLUSTER"] == "arena"
    assert arena["public_access_enabled"] is True
    assert arena["public_ingress_domain"] == "labs.smg-helix.ai"
    assert env["OAUTH2_PROXY_OIDC_ISSUER_URL"] == (
        f"{PUBLIC_ORIGIN}/realms/launchpad-public"
    )
    assert env["OAUTH2_PROXY_LOGIN_URL"] == (
        f"{PUBLIC_ORIGIN}/realms/launchpad-public/protocol/openid-connect/auth"
    )
    assert env["OAUTH2_PROXY_REDIRECT_URL"] == f"{PUBLIC_ORIGIN}/oauth2/callback"
    assert env["OAUTH2_PROXY_REDEEM_URL"].startswith("http://keycloak-service.")
    assert env["OAUTH2_PROXY_OIDC_JWKS_URL"].startswith("http://keycloak-service.")
    assert env["OAUTH2_PROXY_SKIP_OIDC_DISCOVERY"] == "true"
    assert env["OAUTH2_PROXY_INSECURE_OIDC_SKIP_ISSUER_VERIFICATION"] == "false"


def test_keycloak_persists_the_permanent_frontend_issuer_and_checks_it_directly():
    keycloak = yaml.safe_load(
        (ROOT / "deploy/launchpad/public-access/keycloak.yaml").read_text()
    )
    hostname = keycloak["spec"]["hostname"]
    apply_script = (ROOT / "deploy/tunnel-oncluster/apply.sh").read_text()

    assert hostname["hostname"] == PUBLIC_ORIGIN
    assert hostname["backchannelDynamic"] is True
    assert hostname["strict"] is True
    assert "oc patch keycloak keycloak" in apply_script
    rollout_check = (
        'oc rollout status statefulset/keycloak -n "$KEYCLOAK_NAMESPACE" '
        '--timeout=300s'
    )
    assert rollout_check in apply_script
    assert apply_script.index(rollout_check) < apply_script.index(
        "oc port-forward service/keycloak-service"
    )
    assert 'realm["attributes"]["frontendUrl"] = origin' in apply_script
    assert '-X PUT "$KEYCLOAK_ADMIN_URL/admin/realms/launchpad-public"' in apply_script
    assert 'internal_issuer=$(curl -fsS "$KEYCLOAK_ADMIN_URL/realms/launchpad-public/.well-known/openid-configuration"' in apply_script
    assert apply_script.index('realm["attributes"]["frontendUrl"] = origin') < apply_script.index(
        "internal_issuer=$(curl"
    )
    assert '[[ "$internal_issuer" == "$PUBLIC_ORIGIN/realms/launchpad-public" ]]' in apply_script


def test_named_tunnel_source_has_no_disposable_hostname_discovery():
    source = "\n".join(
        path.read_text()
        for path in (
            ROOT / "deploy/tunnel-oncluster/deployment.yaml",
            ROOT / "deploy/tunnel-oncluster/apply.sh",
            ROOT / "deploy/tunnel-oncluster/README.md",
            ROOT / "scripts/start-tunnel.sh",
        )
    )

    assert "trycloudflare.com" not in source
    assert "Waiting for the Cloudflare Quick Tunnel hostname" not in source
    assert "grep -Eo" not in source


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


def test_gateway_cookie_preserves_first_party_samesite_policy():
    router = _router_module()

    cookie = (
        "_oauth2_proxy_csrf=secret; Path=/; Max-Age=900; "
        "HttpOnly; Secure; SameSite=Lax"
    )

    assert router._rewrite_response_cookie(cookie, router.GATEWAY_ORIGIN) == cookie


def test_missing_csrf_cookie_recovers_the_original_lab_path():
    router = _router_module()

    recovery = router._csrf_recovery_url(
        "oauth2/callback",
        {},
        "csrf-state:/labs/intel-llm-cpu-serving-92ee020d",
    )

    assert recovery == (
        "/oauth2/start?rd=%2Flabs%2Fintel-llm-cpu-serving-92ee020d"
    )


def test_csrf_recovery_does_not_override_valid_or_unsafe_callbacks():
    router = _router_module()

    assert router._csrf_recovery_url(
        "oauth2/callback",
        {"_oauth2_proxy_csrf": "present"},
        "csrf-state:/labs/serve",
    ) is None
    assert router._csrf_recovery_url(
        "oauth2/callback",
        {},
        "csrf-state://attacker.example",
    ) is None


def test_tunnel_websocket_keeps_the_public_host_while_dialing_the_gateway_service():
    router = _router_module()

    url, connect_overrides = router._websocket_connection(
        router.GATEWAY_ORIGIN,
        "labs/serve-llms-1234/showroom/terminal/ws",
        "token=abc",
        "pilot.trycloudflare.com",
    )

    assert url == (
        "ws://pilot.trycloudflare.com/"
        "labs/serve-llms-1234/showroom/terminal/ws?token=abc"
    )
    assert connect_overrides == {
        "host": "public-access-gateway.partner-ai-launchpad.svc",
        "port": 8443,
        "proxy": None,
    }


def test_public_terminal_websockets_use_bounded_keepalive_timeouts():
    tunnel_router = (ROOT / "deploy/tunnel-oncluster/router.py").read_text()
    public_gateway = (ROOT / "backend/app/public_gateway.py").read_text()

    for source in (tunnel_router, public_gateway):
        assert "ping_interval=20" in source
        assert "ping_timeout=60" in source
        assert "close_timeout=10" in source


def test_named_tunnel_preserves_runtime_contract_when_reconciled():
    manifest = list(
        yaml.safe_load_all(
            (ROOT / "deploy/tunnel-oncluster/deployment.yaml").read_text()
        )
    )
    deployment = next(item for item in manifest if item["kind"] == "Deployment")
    pod_spec = deployment["spec"]["template"]["spec"]
    containers = {item["name"]: item for item in pod_spec["containers"]}

    router_env = {item["name"]: item for item in containers["router"]["env"]}
    cloudflared_env = {
        item["name"]: item for item in containers["cloudflared"]["env"]
    }
    volumes = {item["name"]: item for item in pod_spec["volumes"]}

    assert router_env["BACKEND_URL"]["value"].endswith("/api/v1")
    assert cloudflared_env["HOME"]["value"] == "/tmp"
    assert volumes["cloudflared-home"]["emptyDir"] == {}
    assert containers["cloudflared"]["volumeMounts"] == [
        {"name": "cloudflared-home", "mountPath": "/tmp"}
    ]
