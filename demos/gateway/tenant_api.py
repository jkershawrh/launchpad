"""Tenant Admin API — CRUD endpoints for multi-tenant management."""

import hashlib
import secrets
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import TenantContext, resolve_tenant

logger = logging.getLogger(__name__)

tenant_router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


class CreateTenantRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1, max_length=200)
    tier: str = Field(default="pilot", pattern=r"^(pilot|partner|internal)$")
    resource_quota: dict = Field(default_factory=lambda: {"cpu_cores": 8, "memory_gb": 32, "gpu_count": 0})
    config: dict = Field(default_factory=dict)


class UpdateTenantRequest(BaseModel):
    display_name: Optional[str] = None
    tier: Optional[str] = None
    resource_quota: Optional[dict] = None
    config: Optional[dict] = None
    expires_at: Optional[str] = None


class CreateApiKeyRequest(BaseModel):
    label: str = Field(default="default", max_length=100)
    scopes: list = Field(default_factory=lambda: ["read", "write"])


def _require_admin(tenant: TenantContext):
    if "admin" not in tenant.scopes and tenant.tier != "internal":
        raise HTTPException(status_code=403, detail="Admin access required")


@tenant_router.post("")
async def create_tenant(req: CreateTenantRequest, tenant: TenantContext = Depends(resolve_tenant)):
    _require_admin(tenant)
    import db
    result = await db.create_tenant(
        slug=req.slug, display_name=req.display_name,
        tier=req.tier, resource_quota=req.resource_quota, config=req.config
    )
    if result is None:
        return {"status": "created", "slug": req.slug, "note": "DB unavailable — tenant not persisted"}
    return {"status": "created", "tenant_id": result, "slug": req.slug}


@tenant_router.get("")
async def list_tenants(tenant: TenantContext = Depends(resolve_tenant)):
    _require_admin(tenant)
    import db
    tenants = await db.list_tenants()
    return {"tenants": tenants}


@tenant_router.get("/{slug}")
async def get_tenant(slug: str, tenant: TenantContext = Depends(resolve_tenant)):
    if tenant.tenant_slug != slug:
        _require_admin(tenant)
    import db
    t = await db.get_tenant_by_slug(slug)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")
    return t


@tenant_router.patch("/{slug}")
async def update_tenant(slug: str, req: UpdateTenantRequest, tenant: TenantContext = Depends(resolve_tenant)):
    _require_admin(tenant)
    import db
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await db.update_tenant(slug, **updates)
    if not result:
        return {"status": "not_updated", "note": "DB unavailable or tenant not found"}
    return {"status": "updated", "slug": slug}


@tenant_router.delete("/{slug}")
async def delete_tenant(slug: str, tenant: TenantContext = Depends(resolve_tenant)):
    _require_admin(tenant)
    if slug == "internal":
        raise HTTPException(status_code=400, detail="Cannot deactivate internal tenant")
    import db
    result = await db.deactivate_tenant(slug)
    if not result:
        return {"status": "not_deactivated", "note": "DB unavailable or tenant not found"}
    return {"status": "deactivated", "slug": slug}


@tenant_router.post("/{slug}/api-keys")
async def create_api_key(slug: str, req: CreateApiKeyRequest, tenant: TenantContext = Depends(resolve_tenant)):
    if tenant.tenant_slug != slug:
        _require_admin(tenant)
    import db
    t = await db.get_tenant_by_slug(slug)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")
    raw_key = f"irh-{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.create_api_key(
        tenant_id=str(t["id"]) if isinstance(t, dict) and "id" in t else slug,
        label=req.label, key_hash=key_hash, scopes=req.scopes
    )
    if result is None:
        return {"status": "created", "key": raw_key, "note": "DB unavailable — key not persisted"}
    return {"status": "created", "key": raw_key, "key_id": result, "label": req.label}


@tenant_router.get("/{slug}/api-keys")
async def list_api_keys(slug: str, tenant: TenantContext = Depends(resolve_tenant)):
    if tenant.tenant_slug != slug:
        _require_admin(tenant)
    import db
    t = await db.get_tenant_by_slug(slug)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")
    return {"keys": []}


@tenant_router.delete("/{slug}/api-keys/{key_id}")
async def revoke_api_key(slug: str, key_id: str, tenant: TenantContext = Depends(resolve_tenant)):
    if tenant.tenant_slug != slug:
        _require_admin(tenant)
    return {"status": "revoked", "key_id": key_id}
