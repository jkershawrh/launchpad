import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import oauth


def _request(headers: list[tuple[bytes, bytes]], host: bytes = b"launchpad.apps.example.com") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"host", host), *headers],
    })


def test_kube_admin_is_admin_without_forwarded_groups(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "TRUSTED_OAUTH_HOSTS", {"launchpad.apps.example.com"})
    user = oauth.get_current_user(_request([(b"x-forwarded-user", b"kube:admin")]))
    assert user.username == "kube:admin"
    assert user.is_admin is True


def test_regular_oauth_user_is_not_admin_without_forwarded_groups(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "TRUSTED_OAUTH_HOSTS", {"launchpad.apps.example.com"})
    user = oauth.get_current_user(_request([(b"x-forwarded-user", b"partner-user")]))
    assert user.username == "partner-user"
    assert user.is_admin is False


def test_forwarded_identity_is_rejected_on_public_api_hostname(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "TRUSTED_OAUTH_HOSTS", {"launchpad.apps.example.com"})
    request = _request(
        [(b"x-forwarded-user", b"kube:admin")],
        host=b"launchpad-api.apps.example.com",
    )
    with pytest.raises(HTTPException) as exc_info:
        oauth.get_current_user(request)
    assert exc_info.value.status_code == 401
