from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import provisioning_service
from app.domain.models import Workshop

router = APIRouter(prefix="/workshops", tags=["workshops"])


class WorkshopCreate(BaseModel):
    tenant_id: str
    catalog_item_id: str
    num_users: int
    ttl: str = "8h"
    ocp_version: str = "4.20"
    purpose: str = "events"


@router.post("", response_model=Workshop, status_code=201)
def create_workshop(body: WorkshopCreate):
    workshop = Workshop(
        tenant_id=body.tenant_id,
        catalog_item_id=body.catalog_item_id,
        num_users=body.num_users,
        ttl=body.ttl,
        ocp_version=body.ocp_version,
        purpose=body.purpose,
    )
    try:
        return provisioning_service.provision_workshop(workshop)
    except ValueError as e:
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


@router.delete("/{workshop_id}", response_model=Workshop)
def delete_workshop(workshop_id: str):
    try:
        return provisioning_service.reclaim_workshop(workshop_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
