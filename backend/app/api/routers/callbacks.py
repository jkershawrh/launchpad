from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import provisioning_service
from app.domain.enums import SessionStatus
from app.domain.models import LifecycleEvent

router = APIRouter(prefix="/callbacks", tags=["callbacks"])


class CleanupResult(BaseModel):
    session_id: str
    result: str
    namespace_deleted: bool = False
    placement_released: bool = False
    errors: List[str] = []


@router.post("/cleanup-result")
def cleanup_callback(body: CleanupResult) -> Dict[str, Any]:
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
