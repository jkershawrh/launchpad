import pytest

from app.domain.enums import SessionStatus, ValidationResultStatus
from app.domain.lifecycle import (
    InvalidTransitionError,
    ValidationRequiredError,
    transition,
)
from app.domain.models import LabSession, ValidationResult


def _make_session(status: SessionStatus = SessionStatus.REQUESTED, **kwargs):
    return LabSession(
        request_id="req-001",
        tenant_id="partner-oem-a",
        catalog_item_id="inference-overdrive-quickstart",
        namespace="lab-test-001",
        status=status,
        **kwargs,
    )


def test_lab_session_lifecycle_allows_requested_to_provisioning():
    session = _make_session(SessionStatus.REQUESTED)
    updated = transition(session, SessionStatus.PROVISIONING)
    assert updated.status == SessionStatus.PROVISIONING
    assert len(updated.lifecycle_events) == 1
    assert updated.lifecycle_events[0].from_status == SessionStatus.REQUESTED
    assert updated.lifecycle_events[0].to_status == SessionStatus.PROVISIONING


def test_lab_session_lifecycle_blocks_ready_to_provisioning():
    session = _make_session(SessionStatus.READY)
    with pytest.raises(InvalidTransitionError) as exc_info:
        transition(session, SessionStatus.PROVISIONING)
    assert exc_info.value.from_status == SessionStatus.READY
    assert exc_info.value.to_status == SessionStatus.PROVISIONING


def test_lab_session_requires_validation_before_ready():
    session = _make_session(SessionStatus.VALIDATING)
    with pytest.raises(ValidationRequiredError):
        transition(session, SessionStatus.READY)


def test_lab_session_ready_with_passing_validation():
    vr = ValidationResult(
        session_id="s1",
        check_name="smoke-test",
        result=ValidationResultStatus.PASS,
        message="OK",
    )
    session = _make_session(SessionStatus.VALIDATING, validation_results=[vr])
    updated = transition(session, SessionStatus.READY)
    assert updated.status == SessionStatus.READY


def test_lab_session_blocks_ready_with_failing_validation():
    vr = ValidationResult(
        session_id="s1",
        check_name="smoke-test",
        result=ValidationResultStatus.FAIL,
        message="endpoint down",
    )
    session = _make_session(SessionStatus.VALIDATING, validation_results=[vr])
    with pytest.raises(ValidationRequiredError):
        transition(session, SessionStatus.READY)


def test_full_happy_path_lifecycle():
    session = _make_session()
    session = transition(session, SessionStatus.PROVISIONING)
    session = transition(session, SessionStatus.VALIDATING)
    vr = ValidationResult(
        session_id=session.session_id,
        check_name="smoke-test",
        result=ValidationResultStatus.PASS,
    )
    session = session.model_copy(update={"validation_results": [vr]})
    session = transition(session, SessionStatus.READY)
    session = transition(session, SessionStatus.ACTIVE)
    assert session.started_at is not None
    session = transition(session, SessionStatus.EXPIRED)
    session = transition(session, SessionStatus.RECLAIMED)
    assert session.status == SessionStatus.RECLAIMED
    assert session.completed_at is not None
    assert len(session.lifecycle_events) == 6


def test_failed_to_reclaimed():
    session = _make_session(SessionStatus.FAILED)
    updated = transition(session, SessionStatus.RECLAIMED)
    assert updated.status == SessionStatus.RECLAIMED


def test_validation_failed_session_can_retry_validation():
    session = _make_session(SessionStatus.VALIDATION_FAILED)
    updated = transition(session, SessionStatus.VALIDATING, reason="validation retried")
    assert updated.status == SessionStatus.VALIDATING


def test_transition_records_reason():
    session = _make_session()
    updated = transition(session, SessionStatus.PROVISIONING, reason="user requested")
    assert updated.lifecycle_events[0].reason == "user requested"
