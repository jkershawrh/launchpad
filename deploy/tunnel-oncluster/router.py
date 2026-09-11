"""On-cluster router for the Cloudflare named tunnel.

Runs as a pod on Arena and routes tunnel traffic to in-cluster services:
  /console/…        → OpenShift Console  (console.openshift-console.svc:443)
  /oauth/…          → OpenShift OAuth    (oauth-openshift.openshift-authentication.svc:443)
  /realms/…         → Keycloak           (keycloak-service.keycloak.svc:8080)
  /resources/…      → Keycloak           (keycloak-service.keycloak.svc:8080)
  everything else   → Public gateway     (public-access-gateway.partner-ai-launchpad.svc:8443)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import ssl
import traceback
from urllib.parse import quote, urlsplit

import httpx
import websockets

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("router")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

NOSSL = ssl.create_default_context()
NOSSL.check_hostname = False
NOSSL.verify_mode = ssl.CERT_NONE

CONSOLE_ORIGIN = os.environ.get(
    "CONSOLE_ORIGIN", "https://console.openshift-console.svc:443"
)
OAUTH_ORIGIN = os.environ.get(
    "OAUTH_ORIGIN", "https://oauth-openshift.openshift-authentication.svc:443"
)
KEYCLOAK_ORIGIN = os.environ.get("KEYCLOAK_ORIGIN", "http://keycloak-service.keycloak.svc:8080")
GATEWAY_ORIGIN = os.environ.get(
    "GATEWAY_ORIGIN", "http://public-access-gateway.partner-ai-launchpad.svc:8443"
)

ARENA_CONSOLE_HOST = "console-openshift-console.apps.arena.fm2aihpcsed.com"
ARENA_OAUTH_HOST = "oauth-openshift.apps.arena.fm2aihpcsed.com"
ARENA_KEYCLOAK_HOST = "keycloak.apps.arena.fm2aihpcsed.com"
KEYCLOAK_INT_ORIGIN = "http://keycloak-service.keycloak.svc:8080"

INFRA01_CONSOLE_HOST = "console-openshift-console.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
INFRA01_OAUTH_HOST = "oauth-openshift.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
INFRA01_API_HOST = "api.ocpv-infra01.dal12.infra.demo.redhat.com:6443"


def _select_upstream(path: str) -> tuple:
    if path.startswith("console/"):
        return CONSOLE_ORIGIN, path[len("console/"):], True
    # The Console SPA must see its normal root-level routes. Mounting it under
    # /console changes window.location.pathname and breaks client-side route
    # matching after OAuth. Keep Launchpad's explicit participant paths on the
    # gateway and send only well-known Console routes to the Console service.
    console_routes = (
        "api/", "apis/", "api-resource-list/", "auth/", "static/",
        "locales/", "k8s/", "topology/", "search/", "catalog/",
        "operatorhub/", "dev-catalog/", "monitoring/", "dashboards/",
        "multicloud/", "ns/", "add/", "import/", "deploy-image/",
        "helm-releases/", "pipelines/", "jobs/", "project-details/",
    )
    if path.startswith(console_routes):
        return CONSOLE_ORIGIN, path, True
    if path.startswith("oauth/"):
        upstream_path = path
        # /oauth/oauth2callback/* is a rewrite artifact — the actual OAuth
        # server path is /oauth2callback/* (no /oauth/ prefix)
        if path.startswith("oauth/oauth2callback/"):
            upstream_path = path[len("oauth/"):]
        return OAUTH_ORIGIN, upstream_path, True
    if path.startswith(("realms/", "resources/", "robots.txt")):
        return KEYCLOAK_ORIGIN, path, False
    return GATEWAY_ORIGIN, path, False


_SAMESITE_RE = re.compile(r";\s*SameSite=\w+", re.IGNORECASE)
_DOMAIN_RE = re.compile(r";\s*Domain=[^;]+", re.IGNORECASE)
_PATH_RE = re.compile(r";\s*Path=[^;]+", re.IGNORECASE)


def _fix_cookie_samesite(
    cookie: str, path_prefix: str = "", same_site: str = "None"
) -> str:
    cookie = _SAMESITE_RE.sub("", cookie)
    cookie = _DOMAIN_RE.sub("", cookie)
    if path_prefix == "console/":
        cookie = _PATH_RE.sub("", cookie)
        cookie += "; Path=/"
    elif path_prefix:
        cookie = _PATH_RE.sub("", cookie)
        cookie += f"; Path=/{path_prefix}"
    elif not _PATH_RE.search(cookie):
        cookie += "; Path=/"

    if "Secure" not in cookie:
        cookie += "; Secure"
    cookie += f"; SameSite={same_site}"
    return cookie


def _rewrite_response_cookie(cookie: str, origin: str) -> str:
    """Rewrite only cookies that cross the Console/OAuth proxy boundary.

    Gateway cookies are already issued for the public first-party origin. In
    particular, oauth2-proxy's CSRF cookie must retain SameSite=Lax so browsers
    send it back after the Keycloak redirect.
    """
    if origin == GATEWAY_ORIGIN:
        return cookie
    if origin == CONSOLE_ORIGIN:
        return _fix_cookie_samesite(cookie, path_prefix="console/")
    if origin == OAUTH_ORIGIN:
        return _fix_cookie_samesite(cookie, path_prefix="oauth/")
    return _fix_cookie_samesite(cookie)


def _csrf_recovery_url(path: str, cookies: dict, state: str) -> str | None:
    """Restart an OAuth flow whose short-lived CSRF cookie was lost."""
    if path != "oauth2/callback" or cookies.get("_oauth2_proxy_csrf"):
        return None
    _, separator, redirect_path = state.partition(":")
    if not separator or not redirect_path.startswith("/") or redirect_path.startswith("//"):
        return None
    return f"/oauth2/start?rd={quote(redirect_path, safe='')}"


def _rewrite_url(value: str, tunnel_host: str) -> str:
    # Only plain-text rewrites. URL-encoded forms (redirect_uri params in
    # query strings) must NOT be rewritten or OAuth token exchanges will
    # fail with redirect_uri mismatch errors.
    pairs = [
        (f"https://{ARENA_CONSOLE_HOST}", f"https://{tunnel_host}"),
        (f"https://{ARENA_OAUTH_HOST}", f"https://{tunnel_host}/oauth"),
        (f"https://{INFRA01_CONSOLE_HOST}", f"https://{tunnel_host}"),
        (f"https://{INFRA01_OAUTH_HOST}", f"https://{tunnel_host}/oauth"),
        (f"https://{ARENA_KEYCLOAK_HOST}", f"https://{tunnel_host}"),
        (KEYCLOAK_INT_ORIGIN, f"https://{tunnel_host}"),
    ]
    for old, new in pairs:
        value = value.replace(old, new)
    value = value.replace(
        f"https://{INFRA01_API_HOST}",
        "https://api.arena.fm2aihpcsed.com:6443",
    )
    # Normalize callbacks created by an already-running prefixed Console
    # session. New sessions use the root-level Console SPA routes above.
    value = value.replace(
        f"https://{tunnel_host}/console/",
        f"https://{tunnel_host}/",
    )
    # Older provisioned Showrooms point at the Developer Topology route. A
    # namespace-scoped participant may not have that perspective, while the
    # core Pods page is present for every authenticated OpenShift user.
    value = re.sub(
        rf"https://{re.escape(tunnel_host)}/topology/ns/"
        r"([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)",
        rf"https://{tunnel_host}/k8s/ns/\1/core~v1~Pod",
        value,
    )
    value = value.replace(f"https://{tunnel_host}/oauth/oauth/", f"https://{tunnel_host}/oauth/")
    return value


def _canonical_public_path(path: str) -> str:
    """Remove the legacy prefix so the Console SPA sees its native route."""
    while path.startswith("console/"):
        path = path[len("console/"):]
    topology = re.fullmatch(r"topology/ns/([^/]+)", path)
    if topology:
        return f"k8s/ns/{topology.group(1)}/core~v1~Pod"
    return path


def _rewrite_console_body(body: bytes, tunnel_host: str) -> bytes:
    text = body.decode("utf-8", errors="replace")
    text = _rewrite_url(text, tunnel_host)
    return text.encode("utf-8")


BACKEND_URL = os.environ.get(
    "BACKEND_URL", "http://backend.partner-ai-launchpad.svc:8000/api/v1"
)
BROKER_KEY = os.environ.get("ACCESS_BROKER_KEY", "")
_PUBLIC_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]+)?$", re.IGNORECASE)


def _websocket_connection(
    origin: str,
    upstream_path: str,
    query: str,
    public_host: str,
) -> tuple[str, dict[str, object]]:
    """Build a WebSocket URI without losing the browser-visible Host.

    oauth2-proxy binds its secure session to the public origin.  The tunnel
    still dials the private Service directly, but the WebSocket handshake must
    carry that public Host just like ordinary HTTP requests do.
    """
    parsed = urlsplit(origin)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    uri_host = parsed.netloc
    connect_overrides: dict[str, object] = {}
    normalized_public_host = public_host.strip().casefold()
    if (
        origin.rstrip("/") == GATEWAY_ORIGIN.rstrip("/")
        and _PUBLIC_HOST.fullmatch(normalized_public_host)
        and parsed.hostname
    ):
        uri_host = normalized_public_host
        connect_overrides = {
            "host": parsed.hostname,
            "port": parsed.port or (443 if parsed.scheme == "https" else 80),
            "proxy": None,
        }
    upstream_url = f"{scheme}://{uri_host}/{upstream_path}"
    if query:
        upstream_url += "?" + query
    return upstream_url, connect_overrides


async def _resolve_showroom_ws(headers: dict, path: str) -> str | None:
    """Resolve the Showroom WebSocket URL by making an authenticated HTTP
    request through the gateway's oauth2-proxy (which works for HTTP), then
    connecting the WebSocket directly to the Showroom route (which doesn't
    require auth for terminal connections)."""
    ws_log = logging.getLogger("router.ws")
    tunnel_host = headers.get("host", "")
    cookie = headers.get("cookie", "")

    if not cookie or not tunnel_host:
        ws_log.warning("No cookie or host for WS resolve")
        return None

    try:
        # oauth2-proxy validates the browser session and returns the trusted
        # stable participant username in its auth-response headers.
        auth_url = f"{GATEWAY_ORIGIN}/oauth2/auth"
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.get(
                auth_url,
                headers={"host": tunnel_host, "cookie": cookie},
            )
            username = resp.headers.get("x-auth-request-email", "") or resp.headers.get(
                "x-auth-request-user", ""
            )
            ws_log.info(
                "Resolved username from oauth2: %s (status=%s)",
                username,
                resp.status_code,
            )

        if not username:
            ws_log.warning("Could not resolve username from oauth2/auth")
            return None

        # Now call the backend directly with the broker key
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.get(
                f"{BACKEND_URL}/public-access/private/resolve-identity",
                params={"host": tunnel_host.split(":")[0], "username": username},
                headers={"X-Access-Broker-Key": BROKER_KEY},
            )
            if resp.status_code != 200:
                ws_log.warning("resolve-identity returned %s", resp.status_code)
                return None
            data = resp.json()
            showroom_url = data.get("showroom_url", "")
            if not showroom_url:
                return None

        # Connect WebSocket directly to the Showroom route URL
        ws_path = path
        scheme = "wss" if showroom_url.startswith("https://") else "ws"
        base = showroom_url.split("://", 1)[1].rstrip("/")
        result = f"{scheme}://{base}/{ws_path}"
        ws_log.info("Resolved showroom WS: %s", result)
        return result
    except Exception:
        ws_log.error("resolve failed: %s", traceback.format_exc())
        return None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def route(path: str, request: Request):
    canonical_path = _canonical_public_path(path)
    if canonical_path != path:
        query = f"?{request.url.query}" if request.url.query else ""
        return Response(
            status_code=302,
            headers={"location": f"/{canonical_path}{query}"},
        )
    path = canonical_path
    csrf_recovery = _csrf_recovery_url(
        path,
        request.cookies,
        request.query_params.get("state", ""),
    )
    if csrf_recovery:
        return RedirectResponse(csrf_recovery, status_code=302)

    origin, upstream_path, is_tls = _select_upstream(path)
    tunnel_host = request.headers.get("host", "")

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.casefold() not in {"content-length", "accept-encoding", "connection"}
    }

    if is_tls and origin == CONSOLE_ORIGIN:
        headers["host"] = ARENA_CONSOLE_HOST
    elif is_tls and origin == OAUTH_ORIGIN:
        headers["host"] = ARENA_OAUTH_HOST

    async with httpx.AsyncClient(
        timeout=60, follow_redirects=False, verify=False
    ) as client:
        upstream = await client.request(
            request.method,
            f"{origin}/{upstream_path}",
            params=request.query_params,
            headers=headers,
            content=await request.body(),
        )

    excluded = {
        "content-length", "content-encoding", "connection",
        "transfer-encoding", "set-cookie",
    }
    if is_tls:
        excluded |= {"x-frame-options", "content-security-policy", "content-security-policy-report-only"}

    resp_headers = {
        key: _rewrite_url(value, tunnel_host) if key.casefold() == "location" else value
        for key, value in upstream.headers.items()
        if key.casefold() not in excluded
    }

    body = upstream.content
    content_type = upstream.headers.get("content-type", "")
    is_text_like = (
        "text/" in content_type
        or "yaml" in content_type
        or "json" in content_type
        or "javascript" in content_type
        or "xml" in content_type
        or path.endswith((".yml", ".yaml", ".json", ".js", ".html", ".css"))
    )
    if is_tls and origin == CONSOLE_ORIGIN:
        body = _rewrite_console_body(body, tunnel_host)
    elif is_text_like:
        text = body.decode("utf-8", errors="replace")
        rewritten = _rewrite_url(text, tunnel_host)
        if rewritten != text:
            body = rewritten.encode("utf-8")

    response = Response(
        body,
        status_code=upstream.status_code,
        headers=resp_headers,
    )
    if is_tls:
        response.headers["content-security-policy"] = (
            "frame-ancestors 'self' "
            f"https://{tunnel_host} https://*.apps.arena.fm2aihpcsed.com"
        )
    for cookie in upstream.headers.get_list("set-cookie"):
        response.headers.append("set-cookie", _rewrite_response_cookie(cookie, origin))

    return response


@app.websocket("/{path:path}")
async def websocket_route(path: str, client: WebSocket):
    original_host = client.headers.get("host", "")
    headers = {
        key: value
        for key, value in client.headers.items()
        if key.casefold()
        not in {
            "host",
            "connection",
            "upgrade",
            "sec-websocket-key",
            "sec-websocket-version",
            "sec-websocket-extensions",
        }
    }
    # Preserve the original Host header so oauth2-proxy can validate
    # the session cookie (it was set for the tunnel domain, not the
    # internal service name).
    headers["host"] = original_host

    origin, upstream_path, is_tls = _select_upstream(path)
    upstream_url, connect_overrides = _websocket_connection(
        origin,
        upstream_path,
        client.url.query,
        original_host,
    )

    requested_protocols = [
        value.strip()
        for value in client.headers.get("sec-websocket-protocol", "").split(",")
    ]
    selected_protocol = "tty" if "tty" in requested_protocols else None
    await client.accept(subprotocol=selected_protocol)
    try:
        # For terminal WebSocket: resolve the Showroom URL from the backend
        # and connect directly, bypassing the gateway's oauth2-proxy which
        # doesn't reliably proxy WebSocket upgrades.
        if upstream_path.startswith("terminal/"):
            actual_url = await _resolve_showroom_ws(headers, upstream_path)
            if actual_url:
                upstream_url = actual_url
                connect_overrides = {}

        ws_kwargs = dict(
            additional_headers={k: v for k, v in headers.items() if k.casefold() != "host"},
            subprotocols=[selected_protocol] if selected_protocol else None,
        )
        if upstream_url.startswith("wss://") or is_tls:
            ws_kwargs["ssl"] = NOSSL
        ws_kwargs.update(connect_overrides)

        logging.getLogger("router.ws").info("Connecting WS to %s", upstream_url)

        async with websockets.connect(upstream_url, **ws_kwargs) as upstream:
            async def to_upstream():
                while True:
                    message = await client.receive()
                    if message.get("bytes") is not None:
                        await upstream.send(message["bytes"])
                    elif message.get("text") is not None:
                        await upstream.send(message["text"])
                    else:
                        break

            async def to_client():
                async for message in upstream:
                    if isinstance(message, bytes):
                        await client.send_bytes(message)
                    else:
                        await client.send_text(message)

            tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_client())]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:
        logging.getLogger("router.ws").error("WebSocket error: %s", traceback.format_exc())
