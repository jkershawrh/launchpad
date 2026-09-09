from pathlib import Path

from app.public_gateway import (
    _lab_cards,
    _public_order_prefix,
    _rewrite_showroom_config,
    _rewrite_upstream_content,
    _tool_upstream_url,
    _username,
    app,
)
from fastapi import Response
from fastapi import HTTPException
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
    assert "/labs/{order_ref}/" in paths
    assert "/labs/{order_ref}/showroom/{path:path}" in paths
    assert "/labs/{order_ref}/proxy/tool/{tool_id}/{path:path}" in paths
    assert any(
        route.path == "/labs/{order_ref}/proxy/tool/{tool_id}/{path:path}"
        and route.__class__.__name__ == "APIWebSocketRoute"
        for route in app.routes
    )


def test_gateway_extracts_only_a_valid_order_path_prefix():
    request = type("Request", (), {"url": type("URL", (), {"path": "/labs/serve-llms-ab12cd34/showroom/"})()})()
    assert _public_order_prefix(request) == "/labs/serve-llms-ab12cd34"

    invalid = type("Request", (), {"url": type("URL", (), {"path": "/labs/../admin"})()})()
    assert _public_order_prefix(invalid) == ""


def test_order_home_exposes_only_order_scoped_participant_links(monkeypatch):
    async def resolved(_request):
        return {
            "seat_ref": "seat-1",
            "expires_at": "2026-09-17T20:00:00Z",
            "showroom_url": "https://showroom-seat.apps.arena.fm2aihpcsed.com",
            "workspace_url": "https://rag-seat.apps.arena.fm2aihpcsed.com",
            "console_url": "https://console.example.test",
            "tool_urls": {
                "workspace": "https://rag-seat.apps.arena.fm2aihpcsed.com"
            },
        }

    monkeypatch.setattr("app.public_gateway._resolve", resolved)
    response = TestClient(app).get("/labs/serve-llms-ab12cd34/")

    assert response.status_code == 200
    assert "href='/labs/serve-llms-ab12cd34/showroom/'" in response.text
    assert "href='/labs/serve-llms-ab12cd34/proxy/tool/workspace/'" in response.text
    assert "apps.arena.fm2aihpcsed.com" not in response.text


def test_order_join_form_posts_back_to_the_same_order(monkeypatch):
    async def denied(_request):
        raise HTTPException(403, "Access denied")

    monkeypatch.setattr("app.public_gateway._resolve", denied)
    response = TestClient(app).get("/labs/serve-llms-ab12cd34/")

    assert response.status_code == 200
    assert "action=/labs/serve-llms-ab12cd34/claim" in response.text


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


def test_public_showroom_config_scopes_tool_paths_to_the_selected_order():
    source = """type: showroom
tabs:
  - name: RAG Assistant
    url: https://rag-seat.apps.arena.fm2aihpcsed.com
"""

    config = __import__("yaml").safe_load(
        _rewrite_showroom_config(
            source,
            {"rag": "https://rag-seat.apps.arena.fm2aihpcsed.com"},
            proxy_prefix="/labs/serve-llms-order-123",
        )
    )

    assert config["tabs"][0]["url"] == (
        "/labs/serve-llms-order-123/proxy/tool/rag/"
    )


def test_public_showroom_config_scopes_terminal_to_the_selected_order():
    source = """type: showroom
tabs:
  - name: Terminal
    path: /terminal
    port: 443
"""

    config = __import__("yaml").safe_load(
        _rewrite_showroom_config(
            source,
            {},
            proxy_prefix="/labs/serve-llms-order-123",
        )
    )

    assert config["tabs"][0] == {
        "name": "Terminal",
        "path": "/labs/serve-llms-order-123/showroom/terminal",
        "port": 443,
    }


def test_public_showroom_drops_unentitled_cluster_private_tabs():
    source = """type: showroom
tabs:
  - name: Undeclared workload
    url: https://undeclared-seat.apps.arena.fm2aihpcsed.com
  - name: External documentation
    url: https://docs.redhat.com/example
"""

    config = __import__("yaml").safe_load(
        _rewrite_showroom_config(source, {})
    )

    assert config["tabs"] == [
        {"name": "External documentation", "url": "https://docs.redhat.com/example"}
    ]


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


def test_tool_proxy_rewrites_textual_cluster_urls_to_the_order_mount():
    source = (
        b'<script>window.api="https://rag-seat.apps.arena.fm2aihpcsed.com/api"</script>'
    )

    rewritten = _rewrite_upstream_content(
        source,
        "text/html; charset=utf-8",
        "https://rag-seat.apps.arena.fm2aihpcsed.com",
        "/labs/serve-llms-ab12cd34/proxy/tool/workspace",
    )

    assert b"apps.arena.fm2aihpcsed.com" not in rewritten
    assert b'/labs/serve-llms-ab12cd34/proxy/tool/workspace/api' in rewritten


def test_tool_proxy_rewrites_root_relative_html_assets_to_the_order_mount():
    source = (
        b'<link rel="stylesheet" href="/index.css">'
        b'<script src="/index.js"></script>'
        b'<link rel="manifest" href="/manifest.json">'
    )

    rewritten = _rewrite_upstream_content(
        source,
        "text/html; charset=utf-8",
        "https://rag-seat.apps.arena.fm2aihpcsed.com",
        "/labs/serve-llms-ab12cd34/proxy/tool/workspace",
    )

    assert b'href="/labs/serve-llms-ab12cd34/proxy/tool/workspace/index.css"' in rewritten
    assert b'src="/labs/serve-llms-ab12cd34/proxy/tool/workspace/index.js"' in rewritten
    assert b'href="/labs/serve-llms-ab12cd34/proxy/tool/workspace/manifest.json"' in rewritten


def test_tool_proxy_adapts_anythingllm_bundle_to_the_order_mount():
    source = (
        b'const C={}.VITE_API_BASE||"/api";'
        b'function socket(){return new URL({}.VITE_API_BASE).host}'
        b'const DR=Iz([{path:"/",children:[]}]);'
        b'au.createRoot(document.getElementById("root"));'
        b'const logo="/anything-llm.png";'
    )

    rewritten = _rewrite_upstream_content(
        source,
        "application/javascript; charset=utf-8",
        "https://rag-seat.apps.arena.fm2aihpcsed.com",
        "/labs/serve-llms-ab12cd34/proxy/tool/workspace",
    ).decode()

    mount = "/labs/serve-llms-ab12cd34/proxy/tool/workspace"
    assert f'const C=window.location.origin+"{mount}/api"' in rewritten
    assert f'window.location.host+"{mount}"' in rewritten
    assert f'basename:"{mount}"' in rewritten
    assert f'const logo="{mount}/anything-llm.png"' in rewritten


def test_tool_proxy_does_not_rewrite_binary_content():
    source = b"\x89PNG\r\n\x1a\nhttps://rag-seat.apps.arena.fm2aihpcsed.com"
    assert _rewrite_upstream_content(
        source,
        "image/png",
        "https://rag-seat.apps.arena.fm2aihpcsed.com",
        "/labs/serve-llms-ab12cd34/proxy/tool/workspace",
    ) == source


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


def test_verified_wss_uses_the_websocket_clients_default_tls_context():
    from app import public_gateway

    assert public_gateway.UPSTREAM_TLS_VERIFY is True
    assert public_gateway._websocket_tls_options("wss") == {}
    assert public_gateway._websocket_tls_options("ws") == {}


def test_tool_and_showroom_websockets_share_the_verified_tls_policy():
    source = Path(__file__).resolve().parents[1].joinpath("app/public_gateway.py").read_text()

    assert source.count("**_websocket_tls_options(scheme)") == 2
    assert "ssl=tls" not in source


def test_oauth_proxy_accepts_unverified_participant_identity_labels():
    manifest = (
        Path(__file__).resolve().parents[2] / "deploy/launchpad/base/public-access-gateway.yaml"
    ).read_text()
    assert "--insecure-oidc-allow-unverified-email=true" in manifest
    assert "--oidc-email-claim=preferred_username" in manifest
    assert 'name: PUBLIC_UPSTREAM_TLS_VERIFY, value: "true"' in manifest
