"""Disposable local router for a single-host Cloudflare Quick Tunnel pilot.

Routing:
  /console/…        → OpenShift Console  (localhost:18089, TLS)
  /oauth/…          → OpenShift OAuth    (localhost:18088, TLS)
  /realms/…         → Keycloak           (localhost:18087, plain HTTP)
  /resources/…      → Keycloak           (localhost:18087, plain HTTP)
  everything else   → Public gateway     (localhost:18085, plain HTTP)
"""

import asyncio
import httpx
import ssl
import websockets
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

NOSSL = ssl.create_default_context()
NOSSL.check_hostname = False
NOSSL.verify_mode = ssl.CERT_NONE

CONSOLE_ORIGIN = "https://127.0.0.1:18089"
OAUTH_ORIGIN = "https://127.0.0.1:18088"
KEYCLOAK_ORIGIN = "http://127.0.0.1:18087"
GATEWAY_ORIGIN = "http://127.0.0.1:18085"

ARENA_CONSOLE_HOST = "console-openshift-console.apps.arena.fm2aihpcsed.com"
ARENA_OAUTH_HOST = "oauth-openshift.apps.arena.fm2aihpcsed.com"

INFRA01_CONSOLE_HOST = "console-openshift-console.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
INFRA01_OAUTH_HOST = "oauth-openshift.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
INFRA01_API_HOST = "api.ocpv-infra01.dal12.infra.demo.redhat.com:6443"


def _select_upstream(path: str) -> tuple[str, str, bool]:
    """Return (origin, upstream_path, is_tls)."""
    if path.startswith("console/"):
        return CONSOLE_ORIGIN, path[len("console/"):], True
    if path.startswith("oauth/"):
        # Keep the full path -- the OAuth server expects /oauth/authorize etc.
        # Our route prefix is "oauth/" but the server's own paths also start
        # with "oauth/", so forward without stripping.
        return OAUTH_ORIGIN, path, True
    if path.startswith(("realms/", "resources/", "robots.txt")):
        return KEYCLOAK_ORIGIN, path, False
    return GATEWAY_ORIGIN, path, False


import re

_SAMESITE_RE = re.compile(r";\s*SameSite=\w+", re.IGNORECASE)


def _fix_cookie_samesite(cookie: str) -> str:
    """Ensure every Set-Cookie from the Console/OAuth is SameSite=None; Secure."""
    cookie = _SAMESITE_RE.sub("", cookie)
    if "Secure" not in cookie:
        cookie += "; Secure"
    cookie += "; SameSite=None"
    return cookie


def _rewrite_url(value: str, tunnel_host: str) -> str:
    """Rewrite arena AND stale infra01 domains back through the tunnel."""
    pairs = [
        (f"https://{ARENA_CONSOLE_HOST}", f"https://{tunnel_host}/console"),
        (f"https://{ARENA_OAUTH_HOST}", f"https://{tunnel_host}/oauth"),
        (f"https://{INFRA01_CONSOLE_HOST}", f"https://{tunnel_host}/console"),
        (f"https://{INFRA01_OAUTH_HOST}", f"https://{tunnel_host}/oauth"),
    ]
    for old, new in pairs:
        value = value.replace(old, new)
        value = value.replace(
            old.replace("://", "%3A%2F%2F").replace("/", "%2F"),
            new.replace("://", "%3A%2F%2F").replace("/", "%2F"),
        )
    value = value.replace(
        f"https://{INFRA01_API_HOST}",
        f"https://api.arena.fm2aihpcsed.com:6443",
    )
    # Fix double-prefix: /oauth/oauth/… → /oauth/…
    value = value.replace(f"https://{tunnel_host}/oauth/oauth/", f"https://{tunnel_host}/oauth/")
    value = value.replace(
        f"https%3A%2F%2F{tunnel_host}%2Foauth%2Foauth%2F",
        f"https%3A%2F%2F{tunnel_host}%2Foauth%2F",
    )
    return value


def _rewrite_location(value: str, tunnel_host: str) -> str:
    return _rewrite_url(value, tunnel_host)


def _rewrite_console_body(body: bytes, tunnel_host: str) -> bytes:
    """Rewrite Console HTML so its auth flow stays within the tunnel domain."""
    text = body.decode("utf-8", errors="replace")
    text = _rewrite_url(text, tunnel_host)
    text = text.replace('<base href="/"/>', '<base href="/console/"/>')
    return text.encode("utf-8")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def route(path: str, request: Request):
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
        key: _rewrite_location(value, tunnel_host) if key.casefold() == "location" else value
        for key, value in upstream.headers.items()
        if key.casefold() not in excluded
    }

    body = upstream.content
    if is_tls and origin == CONSOLE_ORIGIN:
        body = _rewrite_console_body(body, tunnel_host)

    response = Response(
        body,
        status_code=upstream.status_code,
        headers=resp_headers,
    )
    if is_tls:
        response.headers["content-security-policy"] = (
            f"frame-ancestors 'self' https://{tunnel_host} https://*.apps.arena.fm2aihpcsed.com"
        )
    for cookie in upstream.headers.get_list("set-cookie"):
        cookie = _fix_cookie_samesite(cookie)
        response.headers.append("set-cookie", cookie)
    return response


@app.websocket("/{path:path}")
async def websocket_route(path: str, client: WebSocket):
    headers = {key: value for key, value in client.headers.items() if key.casefold() not in {"host", "connection", "upgrade", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions"}}
    public_host = client.headers.get("host", "")
    upstream_url = f"ws://{public_host}/{path}"
    if client.url.query:
        upstream_url += "?" + client.url.query
    requested_protocols = [value.strip() for value in client.headers.get("sec-websocket-protocol", "").split(",")]
    selected_protocol = "tty" if "tty" in requested_protocols else None
    await client.accept(subprotocol=selected_protocol)
    try:
        async with websockets.connect(
            upstream_url,
            host="127.0.0.1",
            port=18085,
            additional_headers=headers,
            subprotocols=[selected_protocol] if selected_protocol else None,
        ) as upstream:
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
    except (WebSocketDisconnect, websockets.WebSocketException):
        pass
