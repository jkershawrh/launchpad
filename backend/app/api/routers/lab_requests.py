from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import provisioning_service, public_access_service
from app.domain.access import ExposurePolicy
from app.auth.oauth import User, can_access_tenant, get_current_user, require_tenant_access
from app.domain.models import LabRequest, LabSession

router = APIRouter(prefix="/lab-requests", tags=["lab-requests"], dependencies=[Depends(get_current_user)])


@router.post("", status_code=201)
def create_lab_request(request: LabRequest, user: User = Depends(get_current_user)):
    require_tenant_access(user, request.tenant_id)
    if request.metadata.get("target_cluster") and not user.is_admin:
        raise HTTPException(403, "Only administrators can override environment placement")
    created = provisioning_service.submit_request(request)
    result = created.model_dump(mode="json")
    if request.exposure_policy == ExposurePolicy.PUBLIC_CODE:
        from datetime import datetime, timedelta
        ttl = request.ttl or "4h"
        amount, unit = int(ttl[:-1]), ttl[-1]
        delta = timedelta(days=amount) if unit == "d" else timedelta(hours=amount)
        policy, plaintext = public_access_service.create_policy(
            order_id=created.request_id,
            order_type="individual",
            catalog_slug=created.catalog_item_id,
            seat_refs=[created.request_id],
            expires_at=datetime.utcnow() + delta,
        )
        result["public_url"] = policy.public_url
        result["one_time_access_code"] = plaintext
    return result


@router.get("", response_model=List[LabRequest])
def list_lab_requests(user: User = Depends(get_current_user)):
    return [request for request in provisioning_service._requests.values() if can_access_tenant(user, request.tenant_id)]


@router.get("/{request_id}", response_model=LabRequest)
def get_lab_request(request_id: str, user: User = Depends(get_current_user)):
    req = provisioning_service.get_request(request_id)
    if not req:
        raise HTTPException(404, f"Lab request {request_id} not found")
    if not can_access_tenant(user, req.tenant_id):
        raise HTTPException(404, f"Lab request {request_id} not found")
    return req


@router.post("/{request_id}/provision", response_model=LabSession, status_code=201)
def provision_lab(request_id: str, user: User = Depends(get_current_user)):
    try:
        request = provisioning_service.get_request(request_id)
        if not request or not can_access_tenant(user, request.tenant_id):
            raise HTTPException(404, f"Lab request {request_id} not found")
        return provisioning_service.provision(request_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
