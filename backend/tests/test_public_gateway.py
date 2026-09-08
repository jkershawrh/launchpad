from pathlib import Path

from app.public_gateway import (
    _lab_cards,
    _rewrite_showroom_config,
    _tool_upstream_url,
    _username,
    app,
)
from fastapi import Response
from fastapi.testclient import TestClient


def test_gateway_exposes_only_public_health_identity():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "public-access-gateway"}


def test_gateway_has_no_openapi_or_admin_surface():
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/admin").status_code == 404


def test_participant_home_renders_resume_links_without_exposing_secrets():
    body = _lab_cards(
        [
            {
                "catalog_slug": "operator-workshop",
                "public_url": "https://operator-123.labs.example.io",
                "expires_at": "2026-09-02T18:00:00Z",
            }
        ]
    )
    assert "operator-workshop" in body
    assert "Resume lab" in body
    assert "https://operator-123.labs.example.io" in body
    assert "code" not in body.casefold()


def test_gateway_exposes_participant_home_and_add_lab_routes():
    paths = {route.path for route in app.routes}
    assert "/my-labs" in paths
    assert "/add-lab" in paths
    assert "/add-lab-by-code" in paths
    assert "/instructions/{path:path}" in paths
    assert "/www/{path:path}" in paths
    assert "/ui-config.yml" in paths
    assert "/terminal/{path:path}" in paths
    assert "/assets/{path:path}" in paths
    assert "/token" in paths
    assert "/ws" in paths
    assert "/proxy/tool/{tool_id}/{path:path}" in paths
    assert any(
        route.path == "/proxy/tool/{tool_id}/{path:path}"
        and route.__class__.__name__ == "APIWebSocketRoute"
        for route in app.routes
    )


def test_http_tool_proxy_is_not_shadowed_by_legacy_proxy_route(monkeypatch):
    async def fake_tool_proxy(tool_id, path, request):
        return Response(f"{tool_id}:{path}")

    monkeypatch.setattr("app.public_gateway.proxy_tool", fake_tool_proxy)

    response = TestClient(app).get("/proxy/tool/workspace/api/ping")

    assert response.status_code == 200
    assert response.text == "workspace:api/ping"


def test_public_showroom_config_rewrites_only_entitled_tool_urls():
    source = """type: showroom
tabs:
  - name: Mortgage AI
    url: https://mortgage-seat.apps.arena.example/chat
  - name: Grafana
    url: https://grafana-seat.apps.arena.example
  - name: Documentation
    url: https://docs.redhat.com/example
"""

    config = __import__("yaml").safe_load(
        _rewrite_showroom_config(
            source,
            {
                "mortgage-ai": "https://mortgage-seat.apps.arena.example",
                "grafana": "https://grafana-seat.apps.arena.example",
            },
        )
    )

    assert config["tabs"][0]["url"] == "/proxy/tool/mortgage-ai/chat"
    assert config["tabs"][1]["url"] == "/proxy/tool/grafana/"
    assert config["tabs"][2]["url"] == "https://docs.redhat.com/example"


def test_public_showroom_hides_uncertified_private_console_tab():
    source = """type: showroom
tabs:
  - name: Instructions
    url: /instructions
  - name: OpenShift Console
    url: https://console-openshift-console.apps.arena.fm2aihpcsed.com/k8s/ns/seat-a/core~v1~Pod
"""

    config = __import__("yaml").safe_load(
        _rewrite_showroom_config(source, {}, public_console_url=None)
    )

    assert config["tabs"] == [{"name": "Instructions", "url": "/instructions"}]


def test_public_showroom_enables_console_only_through_certified_public_proxy():
    source = """type: showroom
tabs:
  - name: OpenShift Console
    url: https://console-openshift-console.apps.arena.fm2aihpcsed.com/k8s/ns/seat-a/core~v1~Pod
"""

    config = __import__("yaml").safe_load(
        _rewrite_showroom_config(
            source,
            {},
            public_console_url="https://console.labs.example.test/k8s/ns/seat-a/core~v1~Pod",
        )
    )

    assert config["tabs"][0]["url"] == "/proxy/console/"


def test_tool_proxy_url_cannot_escape_its_authorized_origin():
    assert (
        _tool_upstream_url("https://mortgage-seat.apps.arena.example", "api/health", "verbose=true")
        == "https://mortgage-seat.apps.arena.example/api/health?verbose=true"
    )

    for path in ("//attacker.example/", "../admin", "%2e%2e/admin"):
        try:
            _tool_upstream_url("https://mortgage-seat.apps.arena.example", path, "")
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe tool path was accepted: {path}")


def test_gateway_uses_generated_per_lab_showroom_config():
    source = Path(__file__).resolve().parents[1].joinpath("app/public_gateway.py").read_text()
    assert source.count('path = "www/ui-config.yml"') == 1
    assert 'return await _showroom_alias(request, "www/ui-config.yml")' in source


def test_participant_shell_uses_launchpad_navigation_and_switch_identity():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    from app.public_gateway import _page

    body = _page("<h1>My labs</h1>").body.decode()
    assert "AI Launchpad" in body
    assert "My Lab Access" in body
    assert "Log out of lab" in body
    assert "/oauth2/sign_out" in body
    assert "/brand/redhat.png" in body
    assert "/brand/intel.png" in body


def test_participant_home_does_not_duplicate_console_outside_showroom():
    source = Path(__file__).resolve().parents[1].joinpath("app/public_gateway.py").read_text()
    assert 'key == "console_url" and target.get("showroom_url")' in source
    assert '("showroom_url", "Open Lab")' in source


def test_my_labs_supports_claiming_another_lab_by_code():
    source = Path(__file__).resolve().parents[1].joinpath("app/public_gateway.py").read_text()
    assert "action=/add-lab-by-code" in source
    assert "/private/claim-identity-by-code" in source


def test_gateway_prefers_stable_oidc_username_claim():
    request = type(
        "Request",
        (),
        {
            "headers": {
                "x-forwarded-user": "40982c65-d541-4fca-a92c-44d38885cd45",
                "x-forwarded-email": "lp-87bd01a6f6c73d54ece70b489ceb3957",
            }
        },
    )()
    assert _username(request) == "lp-87bd01a6f6c73d54ece70b489ceb3957"


def test_gateway_accepts_oauth_proxy_websocket_identity_headers():
    request = type(
        "Request",
        (),
        {
            "headers": {
                "x-auth-request-user": "40982c65-d541-4fca-a92c-44d38885cd45",
                "x-auth-request-email": "lp-87bd01a6f6c73d54ece70b489ceb3957",
            }
        },
    )()
    assert _username(request) == "lp-87bd01a6f6c73d54ece70b489ceb3957"


def test_oauth_proxy_accepts_unverified_participant_identity_labels():
    manifest = (
        Path(__file__).resolve().parents[2] / "deploy/launchpad/base/public-access-gateway.yaml"
    ).read_text()
    assert "--insecure-oidc-allow-unverified-email=true" in manifest
    assert "--oidc-email-claim=preferred_username" in manifest
    assert 'name: PUBLIC_UPSTREAM_TLS_VERIFY, value: "true"' in manifest
