from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.auth.oauth import get_current_user

from app.api.deps import tenant_store
from app.domain.models import Tenant

router = APIRouter(dependencies=[Depends(get_current_user)], prefix="/tenants", tags=["tenants"])


@router.post("", response_model=Tenant, status_code=201)
def create_tenant(tenant: Tenant):
    if tenant_store.get(tenant.tenant_id):
        raise HTTPException(409, f"Tenant {tenant.tenant_id} already exists")
    return tenant_store.create(tenant)


@router.get("", response_model=List[Tenant])
def list_tenants():
    return tenant_store.list_all()


@router.get("/{tenant_id}", response_model=Tenant)
def get_tenant(tenant_id: str):
    tenant = tenant_store.get(tenant_id)
    if not tenant:
        raise HTTPException(404, f"Tenant {tenant_id} not found")
    return tenant
