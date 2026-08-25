from __future__ import annotations

from typing import List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import provisioning_service
from app.domain.models import Workshop

router = APIRouter(prefix="/workshops", tags=["workshops"])


class WorkshopCreate(BaseModel):
    tenant_id: str
    catalog_item_id: str
    num_users: int = Field(ge=1, le=100)
    name: str | None = None
    owner_id: str | None = None
    ttl: str = "8h"
    ocp_version: str = "4.20"
    purpose: str = "events"


@router.post("", response_model=Workshop, status_code=201)
def create_workshop(body: WorkshopCreate, idempotency_key: str | None = Header(default=None)):
    workshop = Workshop(
        tenant_id=body.tenant_id,
        catalog_item_id=body.catalog_item_id,
        num_users=body.num_users,
        name=body.name,
        owner_id=body.owner_id,
        ttl=body.ttl,
        ocp_version=body.ocp_version,
        purpose=body.purpose,
    )
    try:
        return provisioning_service.provision_workshop(workshop, idempotency_key=idempotency_key)
    except ValueError as e:
        if "Idempotency key" in str(e):
            raise HTTPException(409, str(e))
        raise HTTPException(400, str(e))


@router.get("", response_model=List[Workshop])
def list_workshops():
    return list(provisioning_service._workshops.values())


@router.get("/{workshop_id}", response_model=Workshop)
def get_workshop(workshop_id: str):
    workshop = provisioning_service.get_workshop(workshop_id)
    if not workshop:
        raise HTTPException(404, f"Workshop {workshop_id} not found")
    return workshop


@router.get("/{workshop_id}/users")
def get_workshop_users(workshop_id: str):
    try:
        return provisioning_service.get_workshop_users(workshop_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{workshop_id}/capacity")
def get_workshop_capacity(workshop_id: str):
    workshop = provisioning_service.get_workshop(workshop_id)
    if not workshop:
        raise HTTPException(404, f"Workshop {workshop_id} not found")
    can, reason = provisioning_service.check_workshop_capacity(workshop)
    return {"can_provision": can, "reason": reason, "seats_provisioned": len(workshop.session_ids)}


@router.delete("/{workshop_id}", response_model=Workshop)
def delete_workshop(workshop_id: str):
    try:
        return provisioning_service.reclaim_workshop(workshop_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
