from starlette.requests import Request

from app.auth import oauth


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    })


def test_kube_admin_is_admin_without_forwarded_groups(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    user = oauth.get_current_user(_request([(b"x-forwarded-user", b"kube:admin")]))
    assert user.username == "kube:admin"
    assert user.is_admin is True


def test_regular_oauth_user_is_not_admin_without_forwarded_groups(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    user = oauth.get_current_user(_request([(b"x-forwarded-user", b"partner-user")]))
    assert user.username == "partner-user"
    assert user.is_admin is False
