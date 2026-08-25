"""
TDD: Complete lifecycle state matrix.
Tests every valid transition succeeds + every invalid transition raises.
"""
import pytest

from app.domain.enums import SessionStatus, ValidationResultStatus
from app.domain.lifecycle import InvalidTransitionError, ValidationRequiredError, transition, VALID_TRANSITIONS
from app.domain.models import LabSession, ValidationResult


def _session(status=SessionStatus.REQUESTED, **kw):
    defaults = dict(request_id="req-1", tenant_id="t-1", catalog_item_id="c-1")
    defaults.update(kw)
    return LabSession(status=status, **defaults)


def _session_with_validation(status=SessionStatus.VALIDATING, passing=True):
    s = _session(status=status)
    result = ValidationResultStatus.PASS if passing else ValidationResultStatus.FAIL
    vr = ValidationResult(session_id=s.session_id, check_name="test", result=result)
    return s.model_copy(update={"validation_results": [vr]})


# ═══════════════════════════════════════════════════════════════════════════════
# ALL VALID TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidTransitions:

    def test_requested_to_provisioning(self):
        s = transition(_session(SessionStatus.REQUESTED), SessionStatus.PROVISIONING)
        assert s.status == SessionStatus.PROVISIONING

    def test_provisioning_to_validating(self):
        s = transition(_session(SessionStatus.PROVISIONING), SessionStatus.VALIDATING)
        assert s.status == SessionStatus.VALIDATING

    def test_provisioning_to_failed(self):
        s = transition(_session(SessionStatus.PROVISIONING), SessionStatus.FAILED)
        assert s.status == SessionStatus.FAILED

    def test_validating_to_ready(self):
        s = transition(_session_with_validation(passing=True), SessionStatus.READY)
        assert s.status == SessionStatus.READY

    def test_validating_to_validation_failed(self):
        s = transition(_session_with_validation(passing=False), SessionStatus.VALIDATION_FAILED)
        assert s.status == SessionStatus.VALIDATION_FAILED

    def test_ready_to_active(self):
        s = transition(_session(SessionStatus.READY), SessionStatus.ACTIVE)
        assert s.status == SessionStatus.ACTIVE
        assert s.started_at is not None

    def test_ready_to_resetting(self):
        s = transition(_session(SessionStatus.READY), SessionStatus.RESETTING)
        assert s.status == SessionStatus.RESETTING

    def test_active_to_expired(self):
        s = transition(_session(SessionStatus.ACTIVE), SessionStatus.EXPIRED)
        assert s.status == SessionStatus.EXPIRED

    def test_active_to_resetting(self):
        s = transition(_session(SessionStatus.ACTIVE), SessionStatus.RESETTING)
        assert s.status == SessionStatus.RESETTING

    def test_expired_to_resetting(self):
        s = transition(_session(SessionStatus.EXPIRED), SessionStatus.RESETTING)
        assert s.status == SessionStatus.RESETTING

    def test_expired_to_reclaimed(self):
        s = transition(_session(SessionStatus.EXPIRED), SessionStatus.RECLAIMED)
        assert s.status == SessionStatus.RECLAIMED
        assert s.completed_at is not None

    def test_resetting_to_reclaimed(self):
        s = transition(_session(SessionStatus.RESETTING), SessionStatus.RECLAIMED)
        assert s.status == SessionStatus.RECLAIMED

    def test_resetting_to_cleanup_failed(self):
        s = transition(_session(SessionStatus.RESETTING), SessionStatus.CLEANUP_FAILED)
        assert s.status == SessionStatus.CLEANUP_FAILED

    def test_resetting_to_validating(self):
        s = transition(_session(SessionStatus.RESETTING), SessionStatus.VALIDATING)
        assert s.status == SessionStatus.VALIDATING

    def test_failed_to_reclaimed(self):
        s = transition(_session(SessionStatus.FAILED), SessionStatus.RECLAIMED)
        assert s.status == SessionStatus.RECLAIMED

    def test_validation_failed_to_reclaimed(self):
        s = transition(_session(SessionStatus.VALIDATION_FAILED), SessionStatus.RECLAIMED)
        assert s.status == SessionStatus.RECLAIMED

    def test_validation_failed_to_validating(self):
        s = transition(_session(SessionStatus.VALIDATION_FAILED), SessionStatus.VALIDATING)
        assert s.status == SessionStatus.VALIDATING

    def test_cleanup_failed_to_reclaimed(self):
        s = transition(_session(SessionStatus.CLEANUP_FAILED), SessionStatus.RECLAIMED)
        assert s.status == SessionStatus.RECLAIMED

    @pytest.mark.parametrize("status", [
        SessionStatus.REQUESTED,
        SessionStatus.PROVISIONING,
        SessionStatus.VALIDATING,
        SessionStatus.FAILED,
        SessionStatus.VALIDATION_FAILED,
    ])
    def test_incomplete_session_can_enter_cleanup(self, status):
        s = transition(_session(status), SessionStatus.RESETTING)
        assert s.status == SessionStatus.RESETTING

    def test_all_valid_transitions_covered(self):
        assert len(VALID_TRANSITIONS) == 23


# ═══════════════════════════════════════════════════════════════════════════════
# INVALID TRANSITIONS — must raise InvalidTransitionError
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidTransitions:

    @pytest.mark.parametrize("from_status,to_status", [
        (SessionStatus.REQUESTED, SessionStatus.ACTIVE),
        (SessionStatus.REQUESTED, SessionStatus.READY),
        (SessionStatus.REQUESTED, SessionStatus.RECLAIMED),
        (SessionStatus.REQUESTED, SessionStatus.VALIDATING),
        (SessionStatus.PROVISIONING, SessionStatus.ACTIVE),
        (SessionStatus.PROVISIONING, SessionStatus.READY),
        (SessionStatus.PROVISIONING, SessionStatus.RECLAIMED),
        (SessionStatus.VALIDATING, SessionStatus.ACTIVE),
        (SessionStatus.VALIDATING, SessionStatus.PROVISIONING),
        (SessionStatus.VALIDATING, SessionStatus.RECLAIMED),
        (SessionStatus.READY, SessionStatus.PROVISIONING),
        (SessionStatus.READY, SessionStatus.VALIDATING),
        (SessionStatus.READY, SessionStatus.RECLAIMED),
        (SessionStatus.ACTIVE, SessionStatus.READY),
        (SessionStatus.ACTIVE, SessionStatus.PROVISIONING),
        (SessionStatus.ACTIVE, SessionStatus.RECLAIMED),
        (SessionStatus.EXPIRED, SessionStatus.ACTIVE),
        (SessionStatus.EXPIRED, SessionStatus.READY),
        (SessionStatus.EXPIRED, SessionStatus.PROVISIONING),
        (SessionStatus.RECLAIMED, SessionStatus.ACTIVE),
        (SessionStatus.RECLAIMED, SessionStatus.READY),
        (SessionStatus.RECLAIMED, SessionStatus.PROVISIONING),
        (SessionStatus.RECLAIMED, SessionStatus.RESETTING),
        (SessionStatus.CLEANUP_FAILED, SessionStatus.ACTIVE),
        (SessionStatus.CLEANUP_FAILED, SessionStatus.READY),
        (SessionStatus.FAILED, SessionStatus.ACTIVE),
        (SessionStatus.FAILED, SessionStatus.READY),
        (SessionStatus.VALIDATION_FAILED, SessionStatus.ACTIVE),
        (SessionStatus.VALIDATION_FAILED, SessionStatus.READY),
    ])
    def test_invalid_transition_raises(self, from_status, to_status):
        with pytest.raises(InvalidTransitionError):
            transition(_session(from_status), to_status)


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION GATE — validating→ready requires passing validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidationGate:

    def test_validating_to_ready_without_results_raises(self):
        with pytest.raises(ValidationRequiredError):
            transition(_session(SessionStatus.VALIDATING), SessionStatus.READY)

    def test_validating_to_ready_with_failures_raises(self):
        with pytest.raises(ValidationRequiredError):
            transition(_session_with_validation(passing=False), SessionStatus.READY)

    def test_validating_to_ready_with_passing_succeeds(self):
        s = transition(_session_with_validation(passing=True), SessionStatus.READY)
        assert s.status == SessionStatus.READY


# ═══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE EVENTS — every transition records an event
# ═══════════════════════════════════════════════════════════════════════════════

class TestLifecycleEvents:

    def test_transition_records_event(self):
        s = transition(_session(), SessionStatus.PROVISIONING, reason="test")
        assert len(s.lifecycle_events) == 1
        assert s.lifecycle_events[0].from_status == SessionStatus.REQUESTED
        assert s.lifecycle_events[0].to_status == SessionStatus.PROVISIONING
        assert s.lifecycle_events[0].reason == "test"

    def test_multiple_transitions_accumulate_events(self):
        s = _session()
        s = transition(s, SessionStatus.PROVISIONING)
        s = transition(s, SessionStatus.VALIDATING)
        assert len(s.lifecycle_events) == 2

    def test_reclaimed_sets_completed_at(self):
        s = transition(_session(SessionStatus.FAILED), SessionStatus.RECLAIMED)
        assert s.completed_at is not None

    def test_active_sets_started_at(self):
        s = transition(_session(SessionStatus.READY), SessionStatus.ACTIVE)
        assert s.started_at is not None
