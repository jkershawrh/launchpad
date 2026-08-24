from __future__ import annotations

from datetime import datetime
from typing import Optional, Set, Tuple

from app.domain.enums import SessionStatus, ValidationResultStatus
from app.domain.models import LabSession, LifecycleEvent


class InvalidTransitionError(Exception):
    def __init__(self, from_status: SessionStatus, to_status: SessionStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid transition: {from_status.value} -> {to_status.value}"
        )


class ValidationRequiredError(Exception):
    pass


VALID_TRANSITIONS: Set[Tuple[SessionStatus, SessionStatus]] = {
    (SessionStatus.REQUESTED, SessionStatus.PROVISIONING),
    (SessionStatus.REQUESTED, SessionStatus.RESETTING),
    (SessionStatus.PROVISIONING, SessionStatus.VALIDATING),
    (SessionStatus.PROVISIONING, SessionStatus.FAILED),
    (SessionStatus.PROVISIONING, SessionStatus.RESETTING),
    (SessionStatus.VALIDATING, SessionStatus.READY),
    (SessionStatus.VALIDATING, SessionStatus.VALIDATION_FAILED),
    (SessionStatus.VALIDATING, SessionStatus.RESETTING),
    (SessionStatus.READY, SessionStatus.ACTIVE),
    (SessionStatus.ACTIVE, SessionStatus.EXPIRED),
    (SessionStatus.ACTIVE, SessionStatus.RESETTING),
    (SessionStatus.EXPIRED, SessionStatus.RESETTING),
    (SessionStatus.EXPIRED, SessionStatus.RECLAIMED),
    (SessionStatus.RESETTING, SessionStatus.RECLAIMED),
    (SessionStatus.RESETTING, SessionStatus.CLEANUP_FAILED),
    (SessionStatus.RESETTING, SessionStatus.VALIDATING),
    (SessionStatus.READY, SessionStatus.RESETTING),
    (SessionStatus.FAILED, SessionStatus.RECLAIMED),
    (SessionStatus.FAILED, SessionStatus.RESETTING),
    (SessionStatus.VALIDATION_FAILED, SessionStatus.RECLAIMED),
    (SessionStatus.VALIDATION_FAILED, SessionStatus.RESETTING),
    (SessionStatus.CLEANUP_FAILED, SessionStatus.RECLAIMED),
}


def transition(
    session: LabSession,
    target: SessionStatus,
    reason: Optional[str] = None,
) -> LabSession:
    current = session.status
    if (current, target) not in VALID_TRANSITIONS:
        raise InvalidTransitionError(current, target)

    if current == SessionStatus.VALIDATING and target == SessionStatus.READY:
        if not session.validation_results:
            raise ValidationRequiredError(
                "Cannot transition to ready: no validation results"
            )
        has_failure = any(
            vr.result == ValidationResultStatus.FAIL
            for vr in session.validation_results
        )
        if has_failure:
            raise ValidationRequiredError(
                "Cannot transition to ready: validation has failures"
            )

    event = LifecycleEvent(
        from_status=current,
        to_status=target,
        timestamp=datetime.utcnow(),
        reason=reason,
    )

    updated = session.model_copy(
        update={
            "status": target,
            "lifecycle_events": session.lifecycle_events + [event],
        }
    )

    if target == SessionStatus.ACTIVE and updated.started_at is None:
        updated = updated.model_copy(update={"started_at": datetime.utcnow()})
    if target == SessionStatus.RECLAIMED:
        updated = updated.model_copy(update={"completed_at": datetime.utcnow()})

    return updated
