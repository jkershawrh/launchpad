"""
Authentication for Partner AI Launchpad.

Three auth methods supported:
1. OAuth proxy headers (X-Forwarded-User) — browser access via SSO
2. API key (X-API-Key header) — programmatic/CLI access
3. Disabled (AUTH_ENABLED=false) — local dev only
"""
from __future__ import annotations

import json
import os

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.oidc import OIDCTokenError, verify_oidc_token


class User(BaseModel):
    username: str
    subject: str | None = None
    email: str | None = None
    groups: list[str] = []
    tenant_ids: list[str] = []
    is_admin: bool = False
    identity_verified: bool = False


AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() != "false"
API_KEYS = set(filter(None, os.environ.get("API_KEYS", "").split(",")))
ADMIN_API_KEYS = set(filter(None, os.environ.get("ADMIN_API_KEYS", "").split(",")))
ADMIN_GROUPS = {"launchpad-admins", "system:cluster-admins", "dedicated-admins"}
ADMIN_USERS = set(filter(None, os.environ.get("ADMIN_USERS", "kube:admin,kubeadmin").split(",")))
TRUSTED_OAUTH_HOSTS = set(filter(None, os.environ.get("TRUSTED_OAUTH_HOSTS", "").split(",")))
OIDC_JWT_HOSTS = set(filter(None, os.environ.get("OIDC_JWT_HOSTS", "").split(",")))


def _tenant_user_map() -> dict[str, list[str]]:
    try:
        value = json.loads(os.environ.get("TENANT_USER_MAP", "{}"))
        return {str(user): [str(tenant) for tenant in tenants] for user, tenants in value.items()}
    except (TypeError, ValueError, AttributeError):
        return {}


def can_access_tenant(user: User, tenant_id: str) -> bool:
    return user.is_admin or tenant_id in user.tenant_ids


def require_tenant_access(user: User, tenant_id: str) -> None:
    if not can_access_tenant(user, tenant_id):
        raise HTTPException(403, f"User {user.username} is not assigned to tenant {tenant_id}.")


def get_current_user(request: Request) -> User:
    if not AUTH_ENABLED:
        return User(
            username="dev-user",
            email="dev@localhost",
            groups=["launchpad-admins"],
            is_admin=True,
        )

    api_key = request.headers.get("X-API-Key")
    if api_key:
        if api_key in ADMIN_API_KEYS:
            return User(username="api-admin", is_admin=True)
        if api_key in API_KEYS or api_key in ADMIN_API_KEYS:
            return User(username="api-user", tenant_ids=_tenant_user_map().get("api-user", []), is_admin=False)
        raise HTTPException(401, "Invalid API key")

    request_host = (request.url.hostname or "").lower()
    if request_host in OIDC_JWT_HOSTS:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "A signed OIDC Bearer token is required")
        try:
            claims = verify_oidc_token(token)
        except OIDCTokenError as exc:
            raise HTTPException(401, "OIDC token validation failed") from exc

        subject = str(claims["sub"])
        username = str(
            claims.get("preferred_username")
            or claims.get("email")
            or subject
        )
        email_value = claims.get("email")
        email = str(email_value) if email_value else None
        groups_claim = claims.get("groups", [])
        groups = [str(group) for group in groups_claim] if isinstance(groups_claim, list) else []
        is_admin = username in ADMIN_USERS or bool(ADMIN_GROUPS & set(groups))
        tenant_ids = set(_tenant_user_map().get(username, []))
        tenant_ids.update(
            group.removeprefix("launchpad-tenant:")
            for group in groups
            if group.startswith("launchpad-tenant:")
        )
        return User(
            subject=subject,
            username=username,
            email=email,
            groups=groups,
            tenant_ids=sorted(tenant_ids),
            is_admin=is_admin,
            identity_verified=True,
        )

    username = request.headers.get("X-Forwarded-User")
    email = request.headers.get("X-Forwarded-Email")
    groups_header = request.headers.get("X-Forwarded-Groups", "")
    groups = [g.strip() for g in groups_header.split(",") if g.strip()]

    if not username:
        raise HTTPException(401, "Not authenticated — provide X-API-Key header or authenticate via SSO")
    if request_host not in TRUSTED_OAUTH_HOSTS:
        raise HTTPException(401, "OAuth identity headers are not accepted on this endpoint")

    is_admin = username in ADMIN_USERS or bool(ADMIN_GROUPS & set(groups))
    tenant_ids = set(_tenant_user_map().get(username, []))
    tenant_ids.update(group.removeprefix("launchpad-tenant:") for group in groups if group.startswith("launchpad-tenant:"))

    return User(
        username=username,
        email=email,
        groups=groups,
        tenant_ids=sorted(tenant_ids),
        is_admin=is_admin,
        identity_verified=True,
    )


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, f"Admin access required. User {user.username} is not in admin groups.")
    return user
