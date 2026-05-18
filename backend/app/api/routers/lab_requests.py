from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from app.api.deps import provisioning_service
from app.domain.enums import LabRequestStatus
from app.domain.models import LabRequest, LabSession

router = APIRouter(prefix="/lab-requests", tags=["lab-requests"])


@router.post("", response_model=LabRequest, status_code=201)
def create_lab_request(request: LabRequest):
    return provisioning_service.submit_request(request)


@router.get("", response_model=List[LabRequest])
def list_lab_requests():
    return list(provisioning_service._requests.values())


@router.get("/{request_id}", response_model=LabRequest)
def get_lab_request(request_id: str):
    req = provisioning_service.get_request(request_id)
    if not req:
        raise HTTPException(404, f"Lab request {request_id} not found")
    return req


@router.post("/{request_id}/provision", response_model=LabSession, status_code=201)
def provision_lab(request_id: str):
    try:
        return provisioning_service.provision(request_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
