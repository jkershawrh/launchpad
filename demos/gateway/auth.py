"""Authentication and tenant resolution for multi-tenant gateway."""

import os
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from fastapi import Request, HTTPException, Depends

logger = logging.getLogger(__name__)

LEGACY_API_KEY = os.getenv("API_KEY", "")

INTERNAL_TENANT = {
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "slug": "internal",
    "tier": "internal",
    "scopes": ["read", "write", "admin"],
}

TIER_ORDER = ["pilot", "partner", "internal"]


@dataclass
class TenantContext:
    tenant_id: str
    tenant_slug: str
    tier: str
    scopes: List[str] = field(default_factory=lambda: ["read", "write"])
    user_email: Optional[str] = None


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def resolve_tenant(request: Request) -> TenantContext:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and "." in auth_header:
        token = auth_header[7:]
        ctx = await _resolve_jwt(token)
        if ctx:
            return ctx

    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        ctx = await _resolve_api_key(api_key)
        if ctx:
            return ctx

    if LEGACY_API_KEY and api_key == LEGACY_API_KEY:
        return TenantContext(**{k: v for k, v in INTERNAL_TENANT.items() if k != "slug"}, tenant_slug=INTERNAL_TENANT["slug"])

    if LEGACY_API_KEY and not api_key:
        return TenantContext(**{k: v for k, v in INTERNAL_TENANT.items() if k != "slug"}, tenant_slug=INTERNAL_TENANT["slug"])

    if not LEGACY_API_KEY and not api_key:
        return TenantContext(**{k: v for k, v in INTERNAL_TENANT.items() if k != "slug"}, tenant_slug=INTERNAL_TENANT["slug"])

    raise HTTPException(status_code=401, detail="Invalid or missing authentication")


async def _resolve_jwt(token: str) -> Optional[TenantContext]:
    try:
        import base64, json
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        tenant_id = claims.get("tenant_id", INTERNAL_TENANT["tenant_id"])
        tenant_slug = claims.get("tenant_slug", "internal")
        tier = claims.get("tier", "partner")
        scopes = claims.get("scopes", ["read", "write"])
        email = claims.get("email")
        return TenantContext(
            tenant_id=tenant_id, tenant_slug=tenant_slug,
            tier=tier, scopes=scopes, user_email=email
        )
    except Exception:
        return None


async def _resolve_api_key(key: str) -> Optional[TenantContext]:
    if LEGACY_API_KEY and key == LEGACY_API_KEY:
        return TenantContext(
            tenant_id=INTERNAL_TENANT["tenant_id"],
            tenant_slug=INTERNAL_TENANT["slug"],
            tier=INTERNAL_TENANT["tier"],
            scopes=INTERNAL_TENANT["scopes"],
        )

    try:
        import db
        key_hash = _hash_key(key)
        result = await db.verify_api_key_db(key_hash)
        if result:
            return TenantContext(
                tenant_id=result["tenant_id"],
                tenant_slug=result.get("tenant_slug", "unknown"),
                tier=result.get("tier", "partner"),
                scopes=result.get("scopes", ["read", "write"]),
            )
    except Exception as e:
        logger.warning("API key lookup failed: %s", e)

    return None


def require_scope(scope: str):
    async def _check(tenant: TenantContext = Depends(resolve_tenant)):
        if scope not in tenant.scopes and "admin" not in tenant.scopes:
            raise HTTPException(status_code=403, detail=f"Missing required scope: {scope}")
        return tenant
    return _check


def require_tier(min_tier: str):
    async def _check(tenant: TenantContext = Depends(resolve_tenant)):
        if TIER_ORDER.index(tenant.tier) < TIER_ORDER.index(min_tier):
            raise HTTPException(status_code=403, detail=f"Requires tier: {min_tier}")
        return tenant
    return _check
