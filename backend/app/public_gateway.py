from __future__ import annotations

import html
import os
from datetime import datetime
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="Launchpad Public Access Gateway", docs_url=None, redoc_url=None, openapi_url=None)
BACKEND = os.getenv("LAUNCHPAD_INTERNAL_API", "http://backend:8000/api/v1").rstrip("/")
BROKER_KEY = os.getenv("ACCESS_BROKER_KEY", "")


def _host(request: Request) -> str:
    return request.headers.get("host", "").split(":", 1)[0].casefold()


async def _resolve(request: Request) -> dict:
    username = request.headers.get("x-forwarded-user", "")
    cookie = request.cookies.get("launchpad_access", "")
    async with httpx.AsyncClient(timeout=10) as client:
        if username:
            result = await client.get(
                f"{BACKEND}/public-access/private/resolve-identity",
                params={"host": _host(request), "username": username},
                headers={"X-Access-Broker-Key": BROKER_KEY},
            )
        else:
            result = await client.get(
                f"{BACKEND}/public-access/private/resolve",
                params={"host": _host(request)},
                headers={"X-Access-Broker-Key": BROKER_KEY},
                cookies={"launchpad_access": cookie},
            )
    if result.status_code != 200:
        raise HTTPException(result.status_code, "Access denied")
    return result.json()


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'><title>Join your lab</title><style>body{{font:16px system-ui;background:#151515;color:#fff;margin:0}}main{{max-width:560px;margin:8vh auto;padding:32px;background:#212121;border:1px solid #444;border-radius:10px}}input,button,a{{box-sizing:border-box;width:100%;padding:13px;margin-top:10px;border-radius:5px}}input{{background:#151515;color:#fff;border:1px solid #888}}button,a{{background:#e00;color:#fff;border:0;font-weight:700;text-decoration:none;display:block;text-align:center}}small{{color:#bbb}}</style></head><body><main>{body}</main></body></html>""")


@app.get("/health")
def health():
    return {"status": "ok", "service": "public-access-gateway"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        target = await _resolve(request)
    except HTTPException:
        return _page("<h1>Join your lab</h1><p>Enter the email label and code supplied by your instructor.</p><small>Email ownership is not verified. The instructor code is the sole secret.</small><form method=post action=/claim><input name=email type=email required placeholder='Email'><input name=code required autocomplete=one-time-code placeholder='Instructor code'><button>Join lab</button></form>")
    links = []
    for key, label in (("showroom_url", "Open visual guide"), ("workspace_url", "Open workspace"), ("console_url", "Open OpenShift Console")):
        if target.get(key):
            path = "/proxy/" + key.removesuffix("_url") + "/"
            links.append(f"<a href='{path}'>{html.escape(label)}</a>")
    return _page(f"<h1>Your lab is ready</h1><p>Seat <strong>{html.escape(target['seat_ref'])}</strong></p>{''.join(links)}<small>Access ends at {html.escape(str(target['expires_at']))}.</small>")


@app.post("/claim")
async def claim(request: Request, email: str = Form(), code: str = Form()):
    host = _host(request)
    async with httpx.AsyncClient(timeout=15) as client:
        policy = await client.get(f"{BACKEND}/public-access/private/order-by-host", params={"host": host}, headers={"X-Access-Broker-Key": BROKER_KEY})
        if policy.status_code != 200:
            return _page("<h1>Access denied</h1><p>Access request cannot be completed.</p>")
        result = await client.post(f"{BACKEND}/public-access/claim", json={"order_id": policy.json()["order_id"], "email": email, "code": code})
    if result.status_code != 200:
        return _page("<h1>Access denied</h1><p>Access request cannot be completed. Check the instructor code.</p>")
    response = RedirectResponse("/", status_code=303)
    cookie = result.cookies.get("launchpad_access")
    if cookie:
        expiry = datetime.fromisoformat(result.json()["session_expires_at"])
        response.set_cookie(
            "launchpad_access", cookie, httponly=True, secure=True, samesite="lax", path="/",
            max_age=max(1, int((expiry - datetime.utcnow()).total_seconds())),
        )
    return response


@app.get("/proxy/{kind}/{path:path}")
async def proxy(kind: str, path: str, request: Request):
    if kind not in {"showroom", "workspace", "console"}:
        raise HTTPException(404)
    target = await _resolve(request)
    base = target.get(f"{kind}_url")
    if not base:
        raise HTTPException(404)
    if kind == "console":
        return RedirectResponse(base, status_code=302)
    url = urljoin(base.rstrip("/") + "/", path)
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        upstream = await client.request(request.method, url, params=request.query_params, headers={"accept": request.headers.get("accept", "*/*")})
    excluded = {"content-length", "connection", "transfer-encoding", "set-cookie"}
    return Response(upstream.content, status_code=upstream.status_code, headers={k: v for k, v in upstream.headers.items() if k.casefold() not in excluded})
