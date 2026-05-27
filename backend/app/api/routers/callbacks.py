from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import provisioning_service
from app.domain.enums import SessionStatus
from app.domain.models import LifecycleEvent

router = APIRouter(prefix="/callbacks", tags=["callbacks"])

INTEGRATION_API_KEY = os.environ.get("INTEGRATION_API_KEY")


def _verify_api_key(request: Request):
    if not INTEGRATION_API_KEY:
        return
    key = request.headers.get("X-API-Key")
    if key != INTEGRATION_API_KEY:
        raise HTTPException(401, "Invalid or missing X-API-Key")


class CleanupResult(BaseModel):
    session_id: str
    result: str
    namespace_deleted: bool = False
    placement_released: bool = False
    errors: List[str] = []


@router.post("/cleanup-result")
def cleanup_callback(body: CleanupResult, request: Request) -> Dict[str, Any]:
    _verify_api_key(request)
    session = provisioning_service.get_session(body.session_id)
    if not session:
        raise HTTPException(404, f"Session {body.session_id} not found")

    if session.status != SessionStatus.CLEANUP_FAILED:
        return {"status": "ignored", "reason": f"Session not in CLEANUP_FAILED state (is {session.status.value})"}

    if body.result == "success":
        event = LifecycleEvent(
            from_status=SessionStatus.CLEANUP_FAILED,
            to_status=SessionStatus.RECLAIMED,
            reason=f"StarGate remediation succeeded — ns_deleted={body.namespace_deleted}, placement_released={body.placement_released}",
        )
        from datetime import datetime
        session = session.model_copy(update={
            "status": SessionStatus.RECLAIMED,
            "completed_at": datetime.utcnow(),
            "lifecycle_events": session.lifecycle_events + [event],
        })
        provisioning_service._save_session(session)
        return {"status": "reclaimed", "session_id": body.session_id}
    else:
        return {"status": "still_failed", "session_id": body.session_id, "errors": body.errors}


class RemediationCallback(BaseModel):
    session_id: str
    action: str  # "reset" or "reclaim"
    reason: str
    evidence: Dict[str, Any] = {}


@router.post("/remediation")
def receive_remediation(callback: RemediationCallback, request: Request) -> Dict[str, Any]:
    _verify_api_key(request)
    """Receive remediation suggestions from StarGate."""
    session = provisioning_service.get_session(callback.session_id)
    if not session:
        raise HTTPException(404, f"Session {callback.session_id} not found")

    if callback.action == "reset":
        if session.status not in (SessionStatus.ACTIVE, SessionStatus.READY):
            return {
                "status": "ignored",
                "reason": f"Session not in resettable state (is {session.status.value})",
            }
        try:
            provisioning_service.reset_session(callback.session_id)
            return {
                "status": "accepted",
                "action": "reset",
                "session_id": callback.session_id,
            }
        except (ValueError, Exception) as e:
            return {"status": "error", "reason": str(e)}

    elif callback.action == "reclaim":
        try:
            provisioning_service.reclaim_session(callback.session_id)
            return {
                "status": "accepted",
                "action": "reclaim",
                "session_id": callback.session_id,
            }
        except (ValueError, Exception):
            try:
                provisioning_service.force_reclaim_session(callback.session_id)
                return {
                    "status": "accepted",
                    "action": "force_reclaim",
                    "session_id": callback.session_id,
                }
            except Exception as e2:
                return {"status": "error", "reason": str(e2)}

    else:
        return {
            "status": "ignored",
            "reason": f"Unknown action: {callback.action}",
        }
