"""
Red Hat SSO / OpenShift OAuth integration.

On OpenShift: oauth-proxy sidecar handles authentication and passes
X-Forwarded-User and X-Forwarded-Email headers to the backend.

For local dev: AUTH_ENABLED=false (default) skips auth.
For cluster: AUTH_ENABLED=true requires valid headers from oauth-proxy.
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


AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"

ADMIN_GROUPS = {"launchpad-admins", "system:cluster-admins", "dedicated-admins"}


def get_current_user(request: Request) -> User:
    if not AUTH_ENABLED:
        return User(
            username="dev-user",
            email="dev@localhost",
            groups=["launchpad-admins"],
            is_admin=True,
        )

    username = request.headers.get("X-Forwarded-User")
    email = request.headers.get("X-Forwarded-Email")
    groups_header = request.headers.get("X-Forwarded-Groups", "")
    groups = [g.strip() for g in groups_header.split(",") if g.strip()]

    if not username:
        raise HTTPException(401, "Not authenticated — missing X-Forwarded-User header")

    is_admin = bool(ADMIN_GROUPS & set(groups))

    return User(username=username, email=email, groups=groups, is_admin=is_admin)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, f"Admin access required. User {user.username} is not in admin groups.")
    return user
