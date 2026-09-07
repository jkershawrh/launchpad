from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import provisioning_service, public_access_service
from app.auth.oauth import (
    User,
    can_access_tenant,
    get_current_user,
    require_tenant_access,
)
from app.domain.access import ExposurePolicy
from app.domain.enums import WorkshopStatus
from app.domain.models import Workshop

router = APIRouter(
    prefix="/workshops",
    tags=["workshops"],
    dependencies=[Depends(get_current_user)],
)


class WorkshopCreate(BaseModel):
    tenant_id: str
    catalog_item_id: str
    num_users: int = Field(ge=1, le=100)
    name: str | None = None
    owner_id: str | None = None
    ttl: str = "8h"
    ocp_version: str = "4.20"
    purpose: str = "events"
    target_cluster: str | None = None
    certification_override: bool = False
    exposure_policy: ExposurePolicy = ExposurePolicy.INTERNAL


class WorkshopResourceEstimate(BaseModel):
    cpu_millicores: int
    memory_mib: int
    pods: int


class WorkshopTransientResourceEstimate(WorkshopResourceEstimate):
    concurrent_seats: int


class WorkshopResourceBreakdown(BaseModel):
    shared: WorkshopResourceEstimate
    per_seat: WorkshopResourceEstimate
    transient: WorkshopTransientResourceEstimate


class WorkshopCapacityPreview(BaseModel):
    can_provision: bool
    reason: str
    seats_requested: int
    selected_cluster: str | None = None
    placement_reason: str | None = None
    catalog_seat_limit: int | None = None
    certification_override: bool = False
    certification_target_seats: int | None = None
    estimated_resources: WorkshopResourceEstimate
    resource_breakdown: WorkshopResourceBreakdown | None = None


class WorkshopOrderResponse(Workshop):
    one_time_access_code: str | None = Field(
        default=None,
        json_schema_extra={"readOnly": True},
    )


def _to_workshop(body: WorkshopCreate) -> Workshop:
    return Workshop(
        tenant_id=body.tenant_id,
        catalog_item_id=body.catalog_item_id,
        num_users=body.num_users,
        name=body.name,
        owner_id=body.owner_id,
        ttl=body.ttl,
        ocp_version=body.ocp_version,
        purpose=body.purpose,
        target_cluster=body.target_cluster,
        certification_override=body.certification_override,
        exposure_policy=body.exposure_policy,
    )


def _authorize_overrides(body: WorkshopCreate, user: User) -> None:
    if body.target_cluster and not user.is_admin:
        raise HTTPException(403, "Only administrators can override workshop placement")
    if body.certification_override and not user.is_admin:
        raise HTTPException(
            403,
            "Only administrators can request an uncertified workshop size",
        )


def _authorized_workshop(workshop_id: str, user: User) -> Workshop:
    workshop = provisioning_service.get_workshop(workshop_id)
    if not workshop or not can_access_tenant(user, workshop.tenant_id):
        raise HTTPException(404, f"Workshop {workshop_id} not found")
    return workshop


@router.post("", response_model=Workshop, status_code=201)
def create_workshop(
    body: WorkshopCreate,
    idempotency_key: str | None = Header(default=None),
    user: User = Depends(get_current_user),
):
    require_tenant_access(user, body.tenant_id)
    _authorize_overrides(body, user)
    workshop = _to_workshop(body)
    try:
        return provisioning_service.provision_workshop(workshop, idempotency_key=idempotency_key)
    except ValueError as e:
        if "Idempotency key" in str(e):
            raise HTTPException(409, str(e))
        raise HTTPException(400, str(e))


@router.get("", response_model=list[Workshop])
def list_workshops(user: User = Depends(get_current_user)):
    return [
        workshop
        for workshop in provisioning_service._workshops.values()
        if can_access_tenant(user, workshop.tenant_id)
    ]


@router.post("/capacity-preview", response_model=WorkshopCapacityPreview)
def preview_workshop_capacity(body: WorkshopCreate, user: User = Depends(get_current_user)):
    require_tenant_access(user, body.tenant_id)
    _authorize_overrides(body, user)
    return provisioning_service.preview_workshop_capacity(_to_workshop(body))


@router.post("/orders", response_model=WorkshopOrderResponse, status_code=201)
def create_workshop_order(
    body: WorkshopCreate,
    idempotency_key: str | None = Header(default=None),
    user: User = Depends(get_current_user),
):
    require_tenant_access(user, body.tenant_id)
    _authorize_overrides(body, user)
    try:
        workshop = provisioning_service.create_workshop_order(
            _to_workshop(body), idempotency_key=idempotency_key
        )
        result = workshop.model_dump(mode="json")
        if body.exposure_policy == ExposurePolicy.PUBLIC_CODE:
            from datetime import datetime, timedelta

            amount, unit = int(body.ttl[:-1]), body.ttl[-1]
            delta = timedelta(days=amount) if unit == "d" else timedelta(hours=amount)
            policy = public_access_service.get_policy(workshop.workshop_id)
            plaintext = None
            if policy is None:
                policy, plaintext = public_access_service.create_policy(
                    order_id=workshop.workshop_id,
                    order_type="workshop",
                    catalog_slug=workshop.catalog_item_id,
                    seat_refs=[seat.seat_id for seat in workshop.seats],
                    expires_at=datetime.utcnow() + delta,
                )
            workshop.public_url = policy.public_url
            provisioning_service._workshops[workshop.workshop_id] = workshop
            result["public_url"] = policy.public_url
            if plaintext:
                result["one_time_access_code"] = plaintext
        return result
    except ValueError as e:
        if "Idempotency key" in str(e):
            raise HTTPException(409, str(e))
        raise HTTPException(400, str(e))


@router.post("/{workshop_id}/confirm", response_model=Workshop, status_code=202)
def confirm_workshop(
    workshop_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    _authorized_workshop(workshop_id, user)
    try:
        workshop = provisioning_service.queue_workshop(workshop_id)
        if workshop.status == WorkshopStatus.QUEUED:
            background_tasks.add_task(provisioning_service.run_queued_workshop, workshop_id)
        return workshop
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(404, str(e))
        raise HTTPException(409, str(e))


@router.get("/{workshop_id}", response_model=Workshop)
def get_workshop(workshop_id: str, user: User = Depends(get_current_user)):
    return _authorized_workshop(workshop_id, user)


@router.post("/{workshop_id}/retry-failed", response_model=Workshop, status_code=202)
def retry_failed_workshop_seats(
    workshop_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    _authorized_workshop(workshop_id, user)
    try:
        workshop = provisioning_service.queue_failed_workshop_seats(workshop_id)
        background_tasks.add_task(provisioning_service.run_queued_workshop, workshop_id)
        return workshop
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(404, str(e))
        raise HTTPException(409, str(e))


@router.get("/{workshop_id}/users")
def get_workshop_users(workshop_id: str, user: User = Depends(get_current_user)):
    _authorized_workshop(workshop_id, user)
    try:
        return provisioning_service.get_workshop_users(workshop_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{workshop_id}/capacity")
def get_workshop_capacity(workshop_id: str, user: User = Depends(get_current_user)):
    workshop = _authorized_workshop(workshop_id, user)
    can, reason = provisioning_service.check_workshop_capacity(workshop)
    return {"can_provision": can, "reason": reason, "seats_provisioned": len(workshop.session_ids)}


@router.delete("/{workshop_id}", response_model=Workshop, status_code=202)
def delete_workshop(
    workshop_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    try:
        current = _authorized_workshop(workshop_id, user)
        if current.status == WorkshopStatus.RECLAIMING:
            return current
        workshop = provisioning_service.queue_workshop_reclaim(workshop_id)
        if workshop.status == WorkshopStatus.RECLAIMING:
            background_tasks.add_task(provisioning_service.reclaim_workshop, workshop_id)
        return workshop
    except ValueError as e:
        raise HTTPException(404, str(e))
