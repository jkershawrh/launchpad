from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.auth.oauth import User, can_access_tenant, get_current_user, require_admin

from app.api.deps import tenant_store
from app.domain.models import Tenant

router = APIRouter(dependencies=[Depends(get_current_user)], prefix="/tenants", tags=["tenants"])


@router.post("", response_model=Tenant, status_code=201, dependencies=[Depends(require_admin)])
def create_tenant(tenant: Tenant):
    if tenant_store.get(tenant.tenant_id):
        raise HTTPException(409, f"Tenant {tenant.tenant_id} already exists")
    return tenant_store.create(tenant)


@router.get("", response_model=List[Tenant])
def list_tenants(user: User = Depends(get_current_user)):
    return [tenant for tenant in tenant_store.list_all() if can_access_tenant(user, tenant.tenant_id)]


@router.get("/{tenant_id}", response_model=Tenant)
def get_tenant(tenant_id: str, user: User = Depends(get_current_user)):
    tenant = tenant_store.get(tenant_id)
    if not tenant:
        raise HTTPException(404, f"Tenant {tenant_id} not found")
    if not can_access_tenant(user, tenant_id):
        raise HTTPException(404, f"Tenant {tenant_id} not found")
    return tenant
