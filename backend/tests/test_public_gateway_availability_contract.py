"""Participant pages must distinguish denial from an unavailable access broker."""

import httpx
from app.public_gateway import app
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_order_home_shows_join_form_for_an_unclaimed_seat(monkeypatch):
    async def denied(_request):
        raise HTTPException(403, "Access denied")

    monkeypatch.setattr("app.public_gateway._resolve", denied)
    response = TestClient(app).get("/labs/serve-llms-ab12cd34/")
    assert response.status_code == 200
    assert "Join your lab" in response.text


def test_order_home_does_not_disguise_broker_outage_as_bad_code(monkeypatch):
    async def unavailable(_request):
        raise HTTPException(503, "Access service unavailable")

    monkeypatch.setattr("app.public_gateway._resolve", unavailable)
    response = TestClient(app).get("/labs/serve-llms-ab12cd34/")
    assert response.status_code == 503
    assert "Join your lab" not in response.text


def test_my_labs_does_not_disguise_broker_outage_as_no_entitlements(monkeypatch):
    async def unavailable(_username):
        raise HTTPException(503, "Access service unavailable")

    monkeypatch.setattr("app.public_gateway._labs_for", unavailable)
    response = TestClient(app).get(
        "/my-labs",
        headers={"x-forwarded-email": "lp-participant-123"},
    )
    assert response.status_code == 503
    assert "No active labs" not in response.text


def test_broker_transport_failure_returns_503_on_order_home(monkeypatch):
    class FailingClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("broker unreachable")

    monkeypatch.setattr("app.public_gateway.httpx.AsyncClient", FailingClient)
    response = TestClient(app).get("/labs/serve-llms-ab12cd34/")
    assert response.status_code == 503


def test_broker_503_does_not_render_an_empty_my_labs_page(monkeypatch):
    class UnavailableClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return httpx.Response(503)

    monkeypatch.setattr("app.public_gateway.httpx.AsyncClient", UnavailableClient)
    response = TestClient(app).get(
        "/my-labs",
        headers={"x-forwarded-email": "lp-participant-123"},
    )
    assert response.status_code == 503
    assert "No active labs" not in response.text
