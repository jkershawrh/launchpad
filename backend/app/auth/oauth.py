"""
Authentication for Partner AI Launchpad.

Three auth methods supported:
1. OAuth proxy headers (X-Forwarded-User) — browser access via SSO
2. API key (X-API-Key header) — programmatic/CLI access
3. Disabled (AUTH_ENABLED=false) — local dev only
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel


class User(BaseModel):
    username: str
    email: Optional[str] = None
    groups: list[str] = []
    is_admin: bool = False


AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() != "false"
API_KEYS = set(filter(None, os.environ.get("API_KEYS", "").split(",")))
ADMIN_API_KEYS = set(filter(None, os.environ.get("ADMIN_API_KEYS", "").split(",")))
ADMIN_GROUPS = {"launchpad-admins", "system:cluster-admins", "dedicated-admins"}
ADMIN_USERS = set(filter(None, os.environ.get("ADMIN_USERS", "kube:admin,kubeadmin").split(",")))
TRUSTED_OAUTH_HOSTS = set(filter(None, os.environ.get("TRUSTED_OAUTH_HOSTS", "").split(",")))


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
            return User(username="api-user", is_admin=False)
        raise HTTPException(401, "Invalid API key")

    username = request.headers.get("X-Forwarded-User")
    email = request.headers.get("X-Forwarded-Email")
    groups_header = request.headers.get("X-Forwarded-Groups", "")
    groups = [g.strip() for g in groups_header.split(",") if g.strip()]

    if not username:
        raise HTTPException(401, "Not authenticated — provide X-API-Key header or authenticate via SSO")
    request_host = (request.url.hostname or "").lower()
    if request_host not in TRUSTED_OAUTH_HOSTS:
        raise HTTPException(401, "OAuth identity headers are not accepted on this endpoint")

    is_admin = username in ADMIN_USERS or bool(ADMIN_GROUPS & set(groups))

    return User(username=username, email=email, groups=groups, is_admin=is_admin)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, f"Admin access required. User {user.username} is not in admin groups.")
    return user
