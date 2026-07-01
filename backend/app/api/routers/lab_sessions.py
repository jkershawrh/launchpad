from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.auth.oauth import get_current_user

from app.api.deps import provisioning_service
from app.domain.lifecycle import InvalidTransitionError, ValidationRequiredError
from app.domain.models import LabSession, ShowbackRecord
from app.domain.reports import HandoffPackage, RepeatabilityReport, SecurityPlan

router = APIRouter(dependencies=[Depends(get_current_user)], prefix="/lab-sessions", tags=["lab-sessions"])


@router.get("", response_model=List[LabSession])
def list_lab_sessions(user: dict = Depends(get_current_user)):
    tenant_id = user.get("tenant_id") or user.get("username", "")
    return [
        s for s in provisioning_service._sessions.values()
        if s.tenant_id == tenant_id
    ]


@router.get("/{session_id}", response_model=LabSession)
def get_lab_session(session_id: str, user: dict = Depends(get_current_user)):
    session = provisioning_service.get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    tenant_id = user.get("tenant_id") or user.get("username", "")
    if session.tenant_id != tenant_id:
        raise HTTPException(404, f"Session {session_id} not found")
    return session


@router.post("/{session_id}/validate", response_model=LabSession)
def validate_session(session_id: str):
    try:
        return provisioning_service.validate_session(session_id)
    except (ValueError, InvalidTransitionError, ValidationRequiredError) as e:
        raise HTTPException(400, str(e))


@router.post("/{session_id}/activate", response_model=LabSession)
def activate_session(session_id: str):
    try:
        return provisioning_service.activate_session(session_id)
    except (ValueError, InvalidTransitionError) as e:
        raise HTTPException(400, str(e))


@router.post("/{session_id}/reset", response_model=LabSession)
def reset_session(session_id: str):
    try:
        return provisioning_service.reset_session(session_id)
    except (ValueError, InvalidTransitionError) as e:
        raise HTTPException(400, str(e))


@router.post("/{session_id}/reclaim", response_model=LabSession)
def reclaim_session(session_id: str):
    try:
        return provisioning_service.reclaim_session(session_id)
    except (ValueError, InvalidTransitionError) as e:
        raise HTTPException(400, str(e))


@router.get("/{session_id}/handoff", response_model=HandoffPackage)
def get_handoff(session_id: str):
    try:
        return provisioning_service.get_handoff(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{session_id}/showback", response_model=ShowbackRecord)
def get_showback(session_id: str):
    try:
        return provisioning_service.get_showback(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{session_id}/repeatability-report", response_model=RepeatabilityReport)
def get_repeatability_report(session_id: str):
    try:
        return provisioning_service.get_repeatability_report(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{session_id}/security-plan", response_model=SecurityPlan)
def get_security_plan(session_id: str):
    try:
        return provisioning_service.get_security_plan(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
