import pytest
from app.api.routers.auth_identity import current_identity
from app.auth import oauth
from fastapi import HTTPException
from starlette.requests import Request


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
    assert user.identity_verified is True


def test_oauth_user_gets_tenants_from_identity_map(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "TRUSTED_OAUTH_HOSTS", {"launchpad.apps.example.com"})
    monkeypatch.setenv("TENANT_USER_MAP", '{"partner-user":["partner-a"]}')

    user = oauth.get_current_user(_request([(b"x-forwarded-user", b"partner-user")]))

    assert user.tenant_ids == ["partner-a"]


def test_oauth_user_gets_tenants_from_group_claims(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "TRUSTED_OAUTH_HOSTS", {"launchpad.apps.example.com"})

    user = oauth.get_current_user(_request([
        (b"x-forwarded-user", b"partner-user"),
        (b"x-forwarded-groups", b"developers,launchpad-tenant:partner-b"),
    ]))

    assert user.tenant_ids == ["partner-b"]


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


def test_oidc_host_requires_a_bearer_token_and_rejects_spoofed_headers(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "OIDC_JWT_HOSTS", {"requester-auth.example.com"})
    request = _request(
        [(b"x-forwarded-user", b"kube:admin")],
        host=b"requester-auth.example.com",
    )

    with pytest.raises(HTTPException) as exc_info:
        oauth.get_current_user(request)

    assert exc_info.value.status_code == 401
    assert "Bearer" in exc_info.value.detail


def test_oidc_claims_are_mapped_to_stable_identity_tenant_and_admin(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "OIDC_JWT_HOSTS", {"requester-auth.example.com"})
    monkeypatch.setattr(
        oauth,
        "verify_oidc_token",
        lambda token: {
            "sub": "authentik-subject-123",
            "preferred_username": "partner-user",
            "email": "partner@example.com",
            "groups": ["launchpad-admins", "launchpad-tenant:partner-b"],
        },
    )

    user = oauth.get_current_user(_request(
        [(b"authorization", b"Bearer signed-token")],
        host=b"requester-auth.example.com",
    ))

    assert user.subject == "authentik-subject-123"
    assert user.username == "partner-user"
    assert user.email == "partner@example.com"
    assert user.tenant_ids == ["partner-b"]
    assert user.is_admin is True
    assert user.identity_verified is True


def test_oidc_host_does_not_fall_back_to_legacy_headers_when_token_is_invalid(monkeypatch):
    monkeypatch.setattr(oauth, "AUTH_ENABLED", True)
    monkeypatch.setattr(oauth, "OIDC_JWT_HOSTS", {"requester-auth.example.com"})

    def reject_token(_token: str):
        raise oauth.OIDCTokenError("signature verification failed")

    monkeypatch.setattr(oauth, "verify_oidc_token", reject_token)
    request = _request(
        [
            (b"authorization", b"Bearer invalid-token"),
            (b"x-forwarded-user", b"kube:admin"),
        ],
        host=b"requester-auth.example.com",
    )

    with pytest.raises(HTTPException) as exc_info:
        oauth.get_current_user(request)

    assert exc_info.value.status_code == 401
    assert "token" in exc_info.value.detail.lower()


def test_current_identity_contract_does_not_expose_groups_or_tenants():
    identity = current_identity(
        oauth.User(
            username="lp-participant",
            email="participant@example.com",
            groups=["private-group"],
            tenant_ids=["tenant-a"],
            is_admin=False,
            identity_verified=True,
        )
    )

    assert identity.model_dump() == {
        "username": "lp-participant",
        "email": "participant@example.com",
        "is_admin": False,
        "identity_verified": True,
    }
