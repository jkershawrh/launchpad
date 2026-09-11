from __future__ import annotations

import asyncio
import html
import os
import re
import ssl
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
import websockets
import yaml
from fastapi import FastAPI, Form, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Launchpad Public Access Gateway", docs_url=None, redoc_url=None, openapi_url=None
)
_logo_dir = Path("/opt/app-root/src/public/logos")
if not _logo_dir.exists():
    _logo_dir = Path(__file__).resolve().parents[2] / "frontend/public/logos"
app.mount("/brand", StaticFiles(directory=_logo_dir), name="participant-brand")
BACKEND = os.getenv("LAUNCHPAD_INTERNAL_API", "http://backend:8000/api/v1").rstrip("/")
BROKER_KEY = os.getenv("ACCESS_BROKER_KEY", "")
UPSTREAM_TLS_VERIFY = os.getenv("PUBLIC_UPSTREAM_TLS_VERIFY", "true").casefold() not in {
    "0",
    "false",
    "no",
}
PROXY_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_PRIVATE_CLUSTER_ROUTE = re.compile(
    r"^(?:[a-z0-9-]+\.)*apps\.[a-z0-9-]+\.fm2aihpcsed\.com$"
)


def _host(request: Request) -> str:
    return request.headers.get("host", "").split(":", 1)[0].casefold()


def _public_order_prefix(request: Request) -> str:
    match = re.match(
        r"^(/labs/[a-z0-9]+(?:-[a-z0-9]+)*)(?:/|$)",
        request.url.path.casefold(),
    )
    return match.group(1) if match else ""


def _username(request: Request) -> str:
    # oauth2-proxy always uses the OIDC subject for X-Forwarded-User.  The
    # configured email claim carries Launchpad's stable preferred_username.
    return (
        request.headers.get("x-forwarded-email", "")
        or request.headers.get("x-auth-request-email", "")
        or request.headers.get("x-forwarded-user", "")
        or request.headers.get("x-auth-request-user", "")
    )


async def _resolve(request: Request) -> dict:
    username = _username(request)
    cookie = request.cookies.get("launchpad_access", "")
    public_path = _public_order_prefix(request)
    async with httpx.AsyncClient(timeout=10) as client:
        if username:
            result = await client.get(
                f"{BACKEND}/public-access/private/resolve-identity",
                params={
                    "host": _host(request),
                    "username": username,
                    "public_path": public_path,
                },
                headers={"X-Access-Broker-Key": BROKER_KEY},
            )
        else:
            result = await client.get(
                f"{BACKEND}/public-access/private/resolve",
                params={"host": _host(request), "public_path": public_path},
                headers={"X-Access-Broker-Key": BROKER_KEY},
                cookies={"launchpad_access": cookie},
            )
    if result.status_code != 200:
        raise HTTPException(result.status_code, "Access denied")
    return result.json()


def _tool_upstream_url(base: str, path: str, query: str) -> str:
    """Join an entitled tool path without permitting an origin escape."""
    decoded = unquote(path)
    if (
        path.startswith(("/", "\\"))
        or decoded.startswith(("/", "\\"))
        or any(part == ".." for part in decoded.replace("\\", "/").split("/"))
    ):
        raise ValueError("Unsafe tool proxy path")
    origin = urlsplit(base)
    if origin.scheme != "https" or not origin.netloc or origin.username:
        raise ValueError("Tool upstream must be an HTTPS origin")
    url = urljoin(base.rstrip("/") + "/", path)
    target = urlsplit(url)
    if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
        raise ValueError("Tool proxy path escaped its authorized origin")
    return f"{url}?{query}" if query else url


def _is_textual_content_type(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().casefold()
    return (
        media_type.startswith("text/")
        or media_type in {
            "application/javascript",
            "application/json",
            "application/manifest+json",
            "application/xml",
            "application/xhtml+xml",
        }
        or media_type.endswith("+json")
        or media_type.endswith("+xml")
    )


def _tool_proxy_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    # A gateway rewrite changes the representation without changing the
    # upstream ETag. Never let an upstream 304 select a browser-cached copy of
    # the older, unrewritten bundle.
    return {
        key: value
        for key, value in headers.items()
        if key.casefold()
        in {"accept", "accept-language", "content-type", "range", "user-agent"}
    }


def _tool_proxy_response_headers(
    headers: Mapping[str, str],
) -> dict[str, str]:
    excluded = {
        "content-length",
        "content-encoding",
        "connection",
        "transfer-encoding",
        "set-cookie",
    }
    if _is_textual_content_type(headers.get("content-type", "")):
        excluded.update({"cache-control", "etag", "expires", "last-modified"})
    response = {
        key: value for key, value in headers.items() if key.casefold() not in excluded
    }
    if _is_textual_content_type(headers.get("content-type", "")):
        response["cache-control"] = "no-store, no-cache, must-revalidate"
    return response


def _rewrite_upstream_content(
    content: bytes,
    content_type: str,
    upstream_origin: str,
    public_mount: str,
) -> bytes:
    """Keep textual tool references on the entitlement-aware public origin."""
    media_type = content_type.split(";", 1)[0].strip().casefold()
    if not _is_textual_content_type(content_type):
        return content
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    upstream = upstream_origin.rstrip("/")
    public = public_mount.rstrip("/")
    source = source.replace(upstream, public)
    source = source.replace(upstream.replace("/", r"\/"), public.replace("/", r"\/"))
    if media_type in {"text/html", "application/xhtml+xml"}:
        # Root-relative Vite assets otherwise escape the entitled tool mount
        # and hit the public gateway root. Keep the document, its assets, and
        # its manifest on the order-scoped proxy path.
        source = re.sub(
            r"(?P<attribute>\b(?:src|href|action)\s*=\s*[\"'])/(?!/)",
            lambda match: f"{match.group('attribute')}{public}/",
            source,
            flags=re.IGNORECASE,
        )
    elif media_type == "application/javascript":
        # AnythingLLM's published image is a Vite SPA compiled for `/` and it
        # does not expose a supported runtime base-path option. Detect its
        # stable VITE_API_BASE signature before applying the narrowly-scoped
        # adapter needed by the entitlement gateway: API calls, WebSockets,
        # React Router navigation, and root-relative image assets all retain
        # the order mount. Unknown JavaScript bundles remain untouched.
        api_pattern = re.compile(
            r'const (?P<name>[$A-Za-z_][$\w]*)=\{\}\.VITE_API_BASE\|\|"/api"'
        )
        source, api_rewrites = api_pattern.subn(
            lambda match: (
                f'const {match.group("name")}=window.location.origin+"{public}/api"'
            ),
            source,
            count=1,
        )
        if api_rewrites == 1:
            # Vite's lazy-chunk preloader prefixes every dependency with `/`.
            # That includes route-specific stylesheets such as github.css, so
            # leaving the generated helper unchanged makes those assets escape
            # the entitled order mount after the SPA first renders.
            source = re.sub(
                r'(?P<prefix>["\']modulepreload["\'],)'
                r'(?P<name>[$A-Za-z_][$\w]*)=function\(e\)\{return"/"\+e\}',
                lambda match: (
                    f'{match.group("prefix")}{match.group("name")}=function(e)'
                    f'{{return"{public}/"+e}}'
                ),
                source,
                count=1,
            )
            source = source.replace(
                "new URL({}.VITE_API_BASE).host",
                f'window.location.host+"{public}"',
            )
            source = re.sub(
                r'\]\}\]\);(?P<react>[$A-Za-z_][$\w]*)\.createRoot\('
                r'document\.getElementById\("root"\)\)',
                lambda match: (
                    f']}}],{{basename:"{public}"}});{match.group("react")}.createRoot('
                    'document.getElementById("root"))'
                ),
                source,
                count=1,
            )
            source = re.sub(
                r'(?P<quote>[\"\'`])/(?!/)(?P<path>[A-Za-z0-9_@./-]+\.'
                r'(?:css|gif|ico|jpe?g|js|json|png|svg|webp|woff2?))(?P=quote)',
                lambda match: (
                    f'{match.group("quote")}{public}/{match.group("path")}'
                    f'{match.group("quote")}'
                ),
                source,
            )
    return source.encode("utf-8")


def _tool_not_ready(tool_id: str) -> HTMLResponse:
    label = html.escape(tool_id.replace("-", " ").title())
    return HTMLResponse(
        _page(
            f"<h1>{label} is not ready yet</h1>"
            "<p>Complete the deployment step in the lab guide, then retry this tab.</p>"
        ).body,
        status_code=503,
        headers={"Retry-After": "5"},
    )


def _websocket_tls_options(scheme: str) -> dict[str, ssl.SSLContext]:
    """Let websockets create its verified context unless verification is disabled."""
    if scheme != "wss" or UPSTREAM_TLS_VERIFY:
        return {}
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return {"ssl": context}


def _rewrite_showroom_config(
    source: str,
    tool_urls: dict[str, str],
    public_console_url: str | None = None,
    proxy_prefix: str = "",
) -> str:
    """Replace only entitled tab URLs with gateway-relative proxy paths."""
    if proxy_prefix:
        if not re.fullmatch(r"/labs/[a-z0-9]+(?:-[a-z0-9]+)*", proxy_prefix):
            raise ValueError("Invalid public order proxy prefix")
        proxy_prefix = proxy_prefix.rstrip("/")
    config = yaml.safe_load(source)
    if not isinstance(config, dict) or not isinstance(config.get("tabs"), list):
        raise TypeError("Showroom UI config is not a tab mapping")
    allowed = sorted(
        ((tool_id, base.rstrip("/")) for tool_id, base in tool_urls.items()),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    rewritten_tabs = []
    for tab in config["tabs"]:
        if (
            proxy_prefix
            and isinstance(tab, dict)
            and isinstance(tab.get("path"), str)
            and tab["path"].startswith("/terminal")
        ):
            tab["path"] = f"{proxy_prefix}/showroom{tab['path']}"
            rewritten_tabs.append(tab)
            continue
        if not isinstance(tab, dict) or not isinstance(tab.get("url"), str):
            rewritten_tabs.append(tab)
            continue
        tab_url = tab["url"]
        tab_host = urlsplit(tab_url).hostname or ""
        if tab_host.startswith("console-openshift-console."):
            if public_console_url:
                tab["url"] = f"{proxy_prefix}/proxy/console/"
                rewritten_tabs.append(tab)
            continue
        entitled = False
        for tool_id, base in allowed:
            if tab_url == base or tab_url.startswith(base + "/"):
                suffix = tab_url[len(base) :].lstrip("/")
                tab["url"] = f"{proxy_prefix}/proxy/tool/{tool_id}/{suffix}"
                entitled = True
                break
        if not entitled and _PRIVATE_CLUSTER_ROUTE.fullmatch(tab_host.casefold()):
            # Never leave a raw execution-cluster route in participant-facing
            # configuration. A catalog declaration and entitlement-aware
            # gateway mapping are required before the tab can be exposed.
            continue
        rewritten_tabs.append(tab)
    config["tabs"] = rewritten_tabs
    return yaml.safe_dump(config, sort_keys=False)


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'><title>Intel × Red Hat AI Launchpad</title><style>
    :root{{--red:#ee0000;--blue:#0071c5;--panel:#212121;--muted:#b8bbbe}}*{{box-sizing:border-box}}body{{font:16px 'Red Hat Text',system-ui,sans-serif;background:radial-gradient(circle at 15% 0,#3b1717 0,transparent 34%),radial-gradient(circle at 90% 20%,#102c43 0,transparent 30%),#151515;color:#fff;margin:0;min-height:100vh}}header{{height:68px;border-bottom:1px solid #353535;background:rgba(21,21,21,.94);display:flex;align-items:center;justify-content:space-between;padding:0 max(24px,calc((100vw - 1120px)/2))}}.brand{{display:flex;align-items:center;gap:12px;font-weight:750;letter-spacing:.01em}}.brand-red{{color:var(--red)}}.brand-intel{{color:#59b8ee}}nav{{display:flex;align-items:center;gap:8px}}nav a{{color:var(--muted);padding:9px 12px;text-decoration:none;border-radius:6px}}nav a:hover{{color:#fff;background:#ffffff12}}main{{max-width:1040px;margin:0 auto;padding:64px 24px 80px}}.panel,section{{background:rgba(33,33,33,.96);border:1px solid #3c3c3c;border-radius:12px;padding:28px;margin-top:20px;box-shadow:0 18px 50px #0005}}h1{{font-size:clamp(30px,5vw,46px);line-height:1.08;margin:0 0 12px}}h2{{margin:0 0 8px}}p{{color:var(--muted);line-height:1.55}}.actions{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:24px}}a.button,button{{display:block;background:var(--red);color:#fff;border:0;border-radius:6px;padding:13px 18px;font-weight:700;text-align:center;text-decoration:none;cursor:pointer}}a.secondary{{background:#2b2b2b;border:1px solid #555}}input{{width:100%;background:#151515;color:#fff;border:1px solid #777;border-radius:6px;padding:13px;margin:7px 0 12px}}small{{display:block;color:#8d9092;margin-top:20px}}.eyebrow{{color:#59b8ee;text-transform:uppercase;font-size:12px;font-weight:800;letter-spacing:.12em}}@media(max-width:700px){{header{{height:auto;padding:18px 22px;align-items:flex-start;gap:15px;flex-direction:column}}main{{padding-top:40px}}}}
    .brand img{{display:block;object-fit:contain}}.brand .redhat{{height:25px;width:auto}}.brand .intel{{height:19px;width:auto}}
    </style></head><body><header><div class='brand'><img class='redhat' src='/brand/redhat.png' alt='Red Hat'><span>×</span><img class='intel' src='/brand/intel.png' alt='Intel'><span style='color:#444'>|</span><span>Partner AI Launchpad</span><span style='font-size:11px;background:#ffffff18;padding:4px 7px;border-radius:4px'>PARTICIPANT</span></div><nav><a href='/'>Current lab</a><a href='/my-labs'>My Lab Access</a><a href='/oauth2/sign_out?rd=%2Frealms%2Flaunchpad-public%2Fprotocol%2Fopenid-connect%2Flogout'>Log out of lab</a></nav></header><main><div class='eyebrow'>Participant workspace</div><div class='panel'>{body}</div></main></body></html>""")


async def _labs_for(username: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{BACKEND}/public-access/private/identity-entitlements",
            params={"username": username},
            headers={"X-Access-Broker-Key": BROKER_KEY},
        )
    if response.status_code != 200:
        return []
    return response.json().get("labs", [])


def _lab_cards(labs: list[dict]) -> str:
    if not labs:
        return "<p>No active labs are associated with this account.</p>"
    cards = []
    for lab in labs:
        label = html.escape(lab.get("catalog_slug") or "Lab environment")
        url = html.escape(lab["public_url"], quote=True)
        expiry = html.escape(str(lab["expires_at"]))
        cards.append(
            f"<section><h2>{label}</h2><p>Available until {expiry}</p><div class='actions'><a class='button' href='{url}'>Resume lab</a></div></section>"
        )
    return "".join(cards)


@app.get("/health")
def health():
    return {"status": "ok", "service": "public-access-gateway"}


@app.get("/", response_class=HTMLResponse)
@app.get("/labs/{order_ref}", response_class=HTMLResponse)
@app.get("/labs/{order_ref}/", response_class=HTMLResponse)
async def home(request: Request, order_ref: str = ""):
    username = _username(request)
    proxy_prefix = _public_order_prefix(request)
    try:
        target = await _resolve(request)
    except HTTPException:
        if username:
            return _page(
                "<h1>Add this lab</h1><p>You are already signed in. Enter only this lab's instructor code.</p>"
                f"<form method=post action={proxy_prefix}/add-lab><input name=code required autocomplete=one-time-code "
                "placeholder='Instructor code'><button>Add lab</button></form><a href='/my-labs'>My Lab Access</a>"
            )
        return _page(
            "<h1>Join your lab</h1><p>Enter the email label and code supplied by your instructor.</p><small>Email ownership is not verified. The instructor code is the sole secret.</small>"
            f"<form method=post action={proxy_prefix}/claim><input name=email type=email required placeholder='Email'>"
            "<input name=code required autocomplete=one-time-code placeholder='Instructor code'><button>Join lab</button></form>"
        )
    links = []
    for key, label in (
        ("showroom_url", "Open Lab"),
        ("workspace_url", "Open workspace"),
        ("console_url", "Open OpenShift Console"),
    ):
        if key == "console_url" and target.get("showroom_url"):
            continue
        if target.get(key):
            if key == "showroom_url" and proxy_prefix:
                path = f"{proxy_prefix}/showroom/"
            elif key == "workspace_url" and "workspace" in target.get("tool_urls", {}):
                path = f"{proxy_prefix}/proxy/tool/workspace/"
            else:
                path = f"{proxy_prefix}/proxy/{key.removesuffix('_url')}/"
            links.append(f"<a class='button' href='{path}'>{html.escape(label)}</a>")
    return _page(
        f"<h1>Your lab is ready</h1><p>Seat <strong>{html.escape(target['seat_ref'])}</strong></p><div class='actions'>{''.join(links)}<a class='button secondary' href='/my-labs'>My Lab Access</a><a class='button secondary' href='/oauth2/sign_out?rd=%2Frealms%2Flaunchpad-public%2Fprotocol%2Fopenid-connect%2Flogout'>Log out of lab</a></div><small>Logging out preserves your seat. Access ends at {html.escape(str(target['expires_at']))}.</small>"
    )


@app.get("/my-labs", response_class=HTMLResponse)
async def my_labs(request: Request):
    username = _username(request)
    if not username:
        return RedirectResponse("/", status_code=302)
    return _page(
        "<h1>My Lab Access</h1><p>Resume any active environment associated with your participant identity.</p>"
        + _lab_cards(await _labs_for(username))
        + "<section><h2>Add another lab</h2><p>Enter the instructor code for another active lab.</p>"
        "<form method=post action=/add-lab-by-code><input name=code required autocomplete=one-time-code "
        "placeholder='Instructor code'><button>Add lab</button></form></section>"
    )


@app.post("/add-lab-by-code")
async def add_lab_by_code(request: Request, code: str = Form()):
    username = _username(request)
    if not username:
        return RedirectResponse("/", status_code=303)
    async with httpx.AsyncClient(timeout=15) as client:
        result = await client.post(
            f"{BACKEND}/public-access/private/claim-identity-by-code",
            json={"username": username, "code": code},
            headers={"X-Access-Broker-Key": BROKER_KEY},
        )
    if result.status_code != 200:
        return _page(
            "<h1>Access denied</h1><p>That code is invalid, expired, or has no available seats.</p><a href='/my-labs'>My Lab Access</a>"
        )
    return RedirectResponse(result.json()["public_url"], status_code=303)


@app.post("/add-lab")
@app.post("/labs/{order_ref}/add-lab")
async def add_lab(request: Request, code: str = Form(), order_ref: str = ""):
    username = _username(request)
    if not username:
        return RedirectResponse("/", status_code=303)
    async with httpx.AsyncClient(timeout=15) as client:
        result = await client.post(
            f"{BACKEND}/public-access/private/claim-identity",
            json={
                "host": _host(request),
                "username": username,
                "code": code,
                "public_path": _public_order_prefix(request),
            },
            headers={"X-Access-Broker-Key": BROKER_KEY},
        )
    if result.status_code != 200:
        return _page(
            "<h1>Access denied</h1><p>Access request cannot be completed. Check the instructor code.</p><a href='/my-labs'>My Lab Access</a>"
        )
    return RedirectResponse(_public_order_prefix(request) or "/", status_code=303)


@app.post("/claim")
@app.post("/labs/{order_ref}/claim")
async def claim(
    request: Request,
    email: str = Form(),
    code: str = Form(),
    order_ref: str = "",
):
    host = _host(request)
    async with httpx.AsyncClient(timeout=15) as client:
        policy = await client.get(
            f"{BACKEND}/public-access/private/order-by-host",
            params={"host": host, "public_path": _public_order_prefix(request)},
            headers={"X-Access-Broker-Key": BROKER_KEY},
        )
        if policy.status_code != 200:
            return _page("<h1>Access denied</h1><p>Access request cannot be completed.</p>")
        result = await client.post(
            f"{BACKEND}/public-access/claim",
            json={"order_id": policy.json()["order_id"], "email": email, "code": code},
        )
    if result.status_code != 200:
        return _page(
            "<h1>Access denied</h1><p>Access request cannot be completed. Check the instructor code.</p>"
        )
    response = RedirectResponse(_public_order_prefix(request) or "/", status_code=303)
    cookie = result.cookies.get("launchpad_access")
    if cookie:
        expiry = datetime.fromisoformat(result.json()["session_expires_at"])
        response.set_cookie(
            "launchpad_access",
            cookie,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            max_age=max(1, int((expiry - datetime.utcnow()).total_seconds())),
        )
    return response


@app.get("/proxy/{kind}/{path:path}")
@app.get("/labs/{order_ref}/proxy/{kind}/{path:path}")
async def proxy(
    kind: str,
    path: str,
    request: Request,
    order_ref: str = "",
):
    # Starlette resolves routes in declaration order.  This legacy catch-all
    # is registered before the more specific HTTP tool proxy below, so forward
    # the tool shape explicitly instead of rejecting it as an unknown kind.
    if kind == "tool":
        tool_id, separator, tool_path = path.partition("/")
        if not tool_id or not separator:
            raise HTTPException(404)
        if order_ref:
            return await proxy_tool(tool_id, tool_path, request, order_ref)
        return await proxy_tool(tool_id, tool_path, request)
    if kind not in {"showroom", "workspace", "console"}:
        raise HTTPException(404)
    target = await _resolve(request)
    base = target.get(f"{kind}_url")
    if not base:
        raise HTTPException(404)
    if kind == "console":
        return RedirectResponse(base, status_code=302)
    if kind == "showroom" and path == "ui-config.yml":
        return await _showroom_alias(request, "www/ui-config.yml")
    url = urljoin(base.rstrip("/") + "/", path)
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=False, verify=UPSTREAM_TLS_VERIFY
    ) as client:
        upstream = await client.request(
            request.method,
            url,
            params=request.query_params,
            headers={"accept": request.headers.get("accept", "*/*")},
        )
    excluded = {
        "content-length",
        "content-encoding",
        "connection",
        "transfer-encoding",
        "set-cookie",
    }
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.casefold() not in excluded},
    )


@app.api_route("/proxy/tool/{tool_id}/{path:path}", methods=PROXY_METHODS)
@app.api_route(
    "/labs/{order_ref}/proxy/tool/{tool_id}/{path:path}", methods=PROXY_METHODS
)
async def proxy_tool(
    tool_id: str,
    path: str,
    request: Request,
    order_ref: str = "",
):
    target = await _resolve(request)
    base = target.get("tool_urls", {}).get(tool_id)
    if not base:
        raise HTTPException(404)
    try:
        url = _tool_upstream_url(base, path, request.url.query)
    except ValueError as exc:
        raise HTTPException(404) from exc
    request_headers = _tool_proxy_request_headers(request.headers)
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=False,
            verify=UPSTREAM_TLS_VERIFY,
        ) as client:
            upstream = await client.request(
                request.method,
                url,
                content=await request.body(),
                headers=request_headers,
            )
    except httpx.RequestError:
        return _tool_not_ready(tool_id)
    response_headers = _tool_proxy_response_headers(upstream.headers)
    public_mount = f"{_public_order_prefix(request)}/proxy/tool/{tool_id}"
    location = response_headers.get("location")
    if location:
        redirected = urljoin(base.rstrip("/") + "/", location)
        parsed_base = urlsplit(base)
        parsed_redirect = urlsplit(redirected)
        if (parsed_redirect.scheme, parsed_redirect.netloc) == (
            parsed_base.scheme,
            parsed_base.netloc,
        ):
            suffix = parsed_redirect.path.lstrip("/")
            response_headers["location"] = f"{public_mount}/{suffix}"
            if parsed_redirect.query:
                response_headers["location"] += f"?{parsed_redirect.query}"
    if (
        upstream.status_code in {502, 503, 504}
        and request.method == "GET"
        and "text/html" in request.headers.get("accept", "")
    ):
        return _tool_not_ready(tool_id)
    content = _rewrite_upstream_content(
        upstream.content,
        upstream.headers.get("content-type", ""),
        base,
        public_mount,
    )
    return Response(
        content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


@app.websocket("/proxy/tool/{tool_id}/{path:path}")
@app.websocket("/labs/{order_ref}/proxy/tool/{tool_id}/{path:path}")
async def proxy_tool_socket(
    client: WebSocket,
    tool_id: str,
    path: str,
    order_ref: str = "",
):
    try:
        target = await _resolve(client)
        base = target.get("tool_urls", {}).get(tool_id)
        if not base:
            await client.close(code=4404)
            return
        https_url = _tool_upstream_url(base, path, client.url.query)
    except (HTTPException, ValueError):
        await client.close(code=4403)
        return
    upstream_url = "wss://" + https_url.removeprefix("https://")
    scheme = urlsplit(upstream_url).scheme
    requested_protocols = [
        value.strip() for value in client.headers.get("sec-websocket-protocol", "").split(",")
    ]
    selected_protocol = next(
        (protocol for protocol in requested_protocols if protocol),
        None,
    )
    await client.accept(subprotocol=selected_protocol)
    try:
        async with websockets.connect(
            upstream_url,
            subprotocols=[selected_protocol] if selected_protocol else None,
            ping_interval=20,
            ping_timeout=60,
            close_timeout=10,
            **_websocket_tls_options(scheme),
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

            tasks = [
                asyncio.create_task(to_upstream()),
                asyncio.create_task(to_client()),
            ]
            _, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except (WebSocketDisconnect, websockets.WebSocketException):
        pass


async def _showroom_alias(
    request: Request,
    path: str,
    proxy_prefix: str = "",
) -> Response:
    target = await _resolve(request)
    base = target.get("showroom_url")
    if not base:
        raise HTTPException(404)
    url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=False, verify=UPSTREAM_TLS_VERIFY
    ) as client:
        upstream = await client.request(
            request.method,
            url,
            params=request.query_params,
            headers={"accept": request.headers.get("accept", "*/*")},
        )
    excluded = {
        "content-length",
        "content-encoding",
        "connection",
        "transfer-encoding",
        "set-cookie",
    }
    content: bytes | str = upstream.content
    if path.lstrip("/") == "www/ui-config.yml" and upstream.status_code == 200:
        try:
            content = _rewrite_showroom_config(
                upstream.content.decode(upstream.encoding or "utf-8"),
                target.get("tool_urls", {}),
                target.get("console_url"),
                proxy_prefix=proxy_prefix,
            )
        except (TypeError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            raise HTTPException(502, "Invalid Showroom UI configuration") from exc
    return Response(
        content,
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.casefold() not in excluded},
    )


@app.api_route("/labs/{order_ref}/showroom", methods=["GET", "HEAD"])
async def order_showroom_redirect(order_ref: str):
    return RedirectResponse(f"/labs/{order_ref}/showroom/", status_code=302)


@app.api_route(
    "/labs/{order_ref}/showroom/{path:path}",
    methods=["GET", "HEAD", "POST"],
)
async def order_showroom(
    request: Request,
    order_ref: str,
    path: str = "",
):
    upstream_path = f"www/{path}" if path == "ui-config.yml" else path
    return await _showroom_alias(
        request,
        upstream_path,
        proxy_prefix=f"/labs/{order_ref}",
    )


@app.api_route("/instructions", methods=["GET", "HEAD"])
@app.api_route("/instructions/{path:path}", methods=["GET", "HEAD"])
async def showroom_instructions(request: Request, path: str = ""):
    if not path:
        return RedirectResponse("/www/modules/index.html", status_code=302)
    return await _showroom_alias(request, f"www/modules/{path}")


@app.api_route("/www/{path:path}", methods=["GET", "HEAD"])
async def showroom_generated_site(request: Request, path: str):
    return await _showroom_alias(request, f"www/{path}")


@app.api_route("/ui-config.yml", methods=["GET", "HEAD"])
@app.api_route("/zero-touch-config.yml", methods=["GET", "HEAD"])
async def showroom_root_config(request: Request):
    path = request.url.path.lstrip("/")
    if path == "ui-config.yml":
        path = "www/ui-config.yml"
    return await _showroom_alias(request, path)


@app.api_route("/terminal", methods=["GET", "HEAD"])
@app.api_route("/terminal/{path:path}", methods=["GET", "HEAD"])
async def showroom_terminal(request: Request, path: str = ""):
    return await _showroom_alias(request, f"terminal/{path}")


@app.api_route("/assets/{path:path}", methods=["GET", "HEAD"])
async def showroom_assets(request: Request, path: str):
    return await _showroom_alias(request, f"www/assets/{path}")


@app.api_route("/token", methods=["GET", "POST"])
async def showroom_terminal_token(request: Request):
    return await _showroom_alias(request, "token")


@app.websocket("/ws")
@app.websocket("/terminal/{path:path}")
@app.websocket("/labs/{order_ref}/showroom/ws")
@app.websocket("/labs/{order_ref}/showroom/terminal/{path:path}")
async def showroom_terminal_socket(
    client: WebSocket,
    path: str = "",
    order_ref: str = "",
):
    try:
        target = await _resolve(client)
    except HTTPException:
        await client.close(code=4403)
        return
    base = target.get("showroom_url")
    if not base:
        await client.close(code=4404)
        return
    scheme = "wss" if base.startswith("https://") else "ws"
    upstream_path = (
        "ws"
        if client.url.path == "/ws" or client.url.path.endswith("/showroom/ws")
        else f"terminal/{path}"
    )
    upstream_url = f"{scheme}://{base.split('://', 1)[-1].rstrip('/')}/{upstream_path}"
    if client.url.query:
        upstream_url += "?" + client.url.query
    requested_protocols = [
        value.strip() for value in client.headers.get("sec-websocket-protocol", "").split(",")
    ]
    selected_protocol = "tty" if "tty" in requested_protocols else None
    await client.accept(subprotocol=selected_protocol)
    try:
        async with websockets.connect(
            upstream_url,
            subprotocols=[selected_protocol] if selected_protocol else None,
            ping_interval=20,
            ping_timeout=60,
            close_timeout=10,
            **_websocket_tls_options(scheme),
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
