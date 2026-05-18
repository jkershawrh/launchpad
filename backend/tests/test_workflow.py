"""
Launch Lab Workflow Rubric — TDD Red/Green Tests

Each workflow step has a GREEN (success) and RED (failure) test.
Steps follow the exact order of execution when a user clicks "Launch Lab".
"""
import pytest

from app.adapters.mock.constraints import FailingConstraintAdapter, MockConstraintAdapter
from app.adapters.mock.pool import MockFullPoolAdapter, MockPoolAdapter
from app.adapters.mock.validation import MockFailingValidationAdapter, MockValidationAdapter
from app.domain.enums import (
    CatalogCategory,
    LabRequestStatus,
    Persistence,
    SessionStatus,
    ValidationResultStatus,
)
from app.domain.lifecycle import InvalidTransitionError, ValidationRequiredError, transition
from app.domain.models import LabRequest, LabSession, ValidationResult
from app.services.provisioning import ProvisioningService


def _make_request(**overrides):
    defaults = dict(
        tenant_id="partner-oem-a",
        requester_id="demo-engineer-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
        persistence=Persistence.EPHEMERAL,
        ttl="4h",
        hardware_profile="gaudi-endpoint",
        quota_profile="standard",
    )
    defaults.update(overrides)
    return LabRequest(**defaults)


def _make_session(status=SessionStatus.REQUESTED, **overrides):
    defaults = dict(
        request_id="req-001",
        tenant_id="partner-oem-a",
        catalog_item_id="inference-overdrive-quickstart",
        namespace="lab-test-001",
        status=status,
    )
    defaults.update(overrides)
    return LabSession(**defaults)


# ─── STEP 1: Submit request with valid catalog item ───────────────────────────

def test_submit_request_accepts_valid_item():
    svc = ProvisioningService()
    req = _make_request()
    result = svc.submit_request(req)
    assert result.status == LabRequestStatus.ACCEPTED


def test_submit_request_rejects_unknown_catalog_item():
    svc = ProvisioningService()
    req = _make_request(catalog_item_id="nonexistent-item")
    result = svc.submit_request(req)
    assert result.status == LabRequestStatus.REJECTED


# ─── STEP 2: Constraint evaluation ───────────────────────────────────────────

def test_submit_request_passes_constraints():
    svc = ProvisioningService(constraints=MockConstraintAdapter())
    req = _make_request()
    result = svc.submit_request(req)
    assert result.status == LabRequestStatus.ACCEPTED


def test_submit_request_blocked_by_constraints():
    svc = ProvisioningService(constraints=FailingConstraintAdapter())
    req = _make_request()
    result = svc.submit_request(req)
    assert result.status == LabRequestStatus.REJECTED


# ─── STEP 3: Request status set correctly ─────────────────────────────────────

def test_accepted_request_has_correct_status():
    svc = ProvisioningService()
    req = _make_request()
    result = svc.submit_request(req)
    assert result.status == LabRequestStatus.ACCEPTED
    stored = svc.get_request(result.request_id)
    assert stored is not None
    assert stored.status == LabRequestStatus.ACCEPTED


def test_rejected_request_has_correct_status():
    svc = ProvisioningService(constraints=FailingConstraintAdapter())
    req = _make_request()
    result = svc.submit_request(req)
    assert result.status == LabRequestStatus.REJECTED
    stored = svc.get_request(result.request_id)
    assert stored.status == LabRequestStatus.REJECTED


# ─── STEP 4: Provision requires accepted request ─────────────────────────────

def test_provision_accepted_request():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    assert session.status == SessionStatus.VALIDATING


def test_provision_rejects_non_accepted_request():
    svc = ProvisioningService(constraints=FailingConstraintAdapter())
    req = svc.submit_request(_make_request())
    assert req.status == LabRequestStatus.REJECTED
    with pytest.raises(ValueError, match="not accepted"):
        svc.provision(req.request_id)


# ─── STEP 5: Provision finds request by ID ───────────────────────────────────

def test_provision_finds_existing_request():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    assert session.request_id == req.request_id


def test_provision_raises_for_missing_request():
    svc = ProvisioningService()
    with pytest.raises(ValueError, match="not found"):
        svc.provision("nonexistent-request-id")


# ─── STEP 6: Pool capacity check + reserve ───────────────────────────────────

def test_pool_reserves_resources():
    pool = MockPoolAdapter()
    svc = ProvisioningService(pool=pool)
    req = svc.submit_request(_make_request())
    svc.provision(req.request_id)
    report = pool.report_allocation()
    assert report["total_reservations"] == 1


def test_pool_rejects_when_no_capacity():
    svc = ProvisioningService(pool=MockFullPoolAdapter())
    req = svc.submit_request(_make_request())
    with pytest.raises(ValueError, match="No capacity available"):
        svc.provision(req.request_id)


# ─── STEP 7: Provisioning plan created ───────────────────────────────────────

def test_plan_created_with_steps():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    svc.provision(req.request_id)
    assert len(svc._plans) == 1
    plan = list(svc._plans.values())[0]
    assert len(plan.steps) == 4
    assert plan.target_namespace is not None


def test_plan_fails_for_missing_catalog_item():
    svc = ProvisioningService()
    req = _make_request(catalog_item_id="nonexistent")
    submitted = svc.submit_request(req)
    assert submitted.status == LabRequestStatus.REJECTED
    with pytest.raises(ValueError):
        svc.provision(submitted.request_id)


# ─── STEP 8: Provisioning executes ───────────────────────────────────────────

def test_provisioning_returns_namespace_and_urls():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    assert session.namespace is not None
    assert session.lab_url is not None
    assert "lab.example.com" in session.lab_url


def test_provisioning_failure_transitions_to_failed():
    session = _make_session(SessionStatus.PROVISIONING)
    failed = transition(session, SessionStatus.FAILED, reason="provisioning error")
    assert failed.status == SessionStatus.FAILED
    assert failed.lifecycle_events[-1].reason == "provisioning error"


# ─── STEP 9: Session created with correct state ──────────────────────────────

def test_session_starts_at_requested():
    session = _make_session()
    assert session.status == SessionStatus.REQUESTED


def test_session_rejects_invalid_initial_status():
    session = _make_session()
    with pytest.raises(InvalidTransitionError):
        transition(session, SessionStatus.READY)


# ─── STEP 10: Transition REQUESTED → PROVISIONING ────────────────────────────

def test_transition_requested_to_provisioning():
    session = _make_session(SessionStatus.REQUESTED)
    updated = transition(session, SessionStatus.PROVISIONING)
    assert updated.status == SessionStatus.PROVISIONING
    assert len(updated.lifecycle_events) == 1


def test_transition_blocks_skip_to_validating():
    session = _make_session(SessionStatus.REQUESTED)
    with pytest.raises(InvalidTransitionError):
        transition(session, SessionStatus.VALIDATING)


# ─── STEP 11: Transition PROVISIONING → VALIDATING ───────────────────────────

def test_transition_provisioning_to_validating():
    session = _make_session(SessionStatus.PROVISIONING)
    updated = transition(session, SessionStatus.VALIDATING)
    assert updated.status == SessionStatus.VALIDATING


def test_transition_blocks_provisioning_to_ready():
    session = _make_session(SessionStatus.PROVISIONING)
    with pytest.raises(InvalidTransitionError):
        transition(session, SessionStatus.READY)


# ─── STEP 12: Validate finds session by ID ───────────────────────────────────

def test_validate_finds_existing_session():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    validated = svc.validate_session(session.session_id)
    assert validated.status == SessionStatus.READY


def test_validate_raises_for_missing_session():
    svc = ProvisioningService()
    with pytest.raises(ValueError, match="not found"):
        svc.validate_session("nonexistent-session-id")


# ─── STEP 13: Validation runs checks ─────────────────────────────────────────

def test_validation_returns_pass_results():
    svc = ProvisioningService(validator=MockValidationAdapter())
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    validated = svc.validate_session(session.session_id)
    assert all(vr.result == ValidationResultStatus.PASS for vr in validated.validation_results)


def test_validation_returns_fail_results():
    svc = ProvisioningService(validator=MockFailingValidationAdapter())
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    validated = svc.validate_session(session.session_id)
    assert validated.status == SessionStatus.VALIDATION_FAILED
    assert any(vr.result == ValidationResultStatus.FAIL for vr in validated.validation_results)


# ─── STEP 14: Transition VALIDATING → READY (all pass) ───────────────────────

def test_transition_validating_to_ready_all_pass():
    vr = ValidationResult(
        session_id="s1", check_name="check", result=ValidationResultStatus.PASS,
    )
    session = _make_session(SessionStatus.VALIDATING, validation_results=[vr])
    updated = transition(session, SessionStatus.READY)
    assert updated.status == SessionStatus.READY


def test_transition_validating_blocked_no_results():
    session = _make_session(SessionStatus.VALIDATING)
    with pytest.raises(ValidationRequiredError):
        transition(session, SessionStatus.READY)


# ─── STEP 15: Transition VALIDATING → VALIDATION_FAILED ──────────────────────

def test_transition_validating_to_validation_failed():
    session = _make_session(SessionStatus.VALIDATING)
    updated = transition(session, SessionStatus.VALIDATION_FAILED)
    assert updated.status == SessionStatus.VALIDATION_FAILED


def test_transition_blocks_ready_with_failures():
    vr = ValidationResult(
        session_id="s1", check_name="check", result=ValidationResultStatus.FAIL,
    )
    session = _make_session(SessionStatus.VALIDATING, validation_results=[vr])
    with pytest.raises(ValidationRequiredError):
        transition(session, SessionStatus.READY)


# ─── STEP 16: Handoff generated for ready session ────────────────────────────

def test_handoff_generated_for_ready_session():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    svc.validate_session(session.session_id)
    handoff = svc.get_handoff(session.session_id)
    assert handoff.lab_title == "Inference Overdrive Quick Start"
    assert handoff.lab_url is not None
    assert "Your AI Lab is Ready" in handoff.to_markdown()


def test_handoff_raises_for_missing_session():
    svc = ProvisioningService()
    with pytest.raises(ValueError, match="not found"):
        svc.get_handoff("nonexistent-session-id")


# ─── STEP 17: Showback record created ────────────────────────────────────────

def test_showback_created_for_session():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    showback = svc.get_showback(session.session_id)
    assert showback.tenant_id == "partner-oem-a"
    assert showback.duration_seconds > 0


def test_showback_raises_for_missing_session():
    svc = ProvisioningService()
    with pytest.raises(ValueError, match="not found"):
        svc.get_showback("nonexistent-session-id")


# ─── STEP 18: Repeatability score ────────────────────────────────────────────

def test_repeatability_score_100_for_complete():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    svc.validate_session(session.session_id)
    report = svc.get_repeatability_report(session.session_id)
    assert report.repeatability_score == 100
    assert report.catalog_versioned is True
    assert report.provisioning_plan_generated is True
    assert report.validation_passed is True


def test_repeatability_score_partial_for_incomplete():
    svc = ProvisioningService(validator=MockFailingValidationAdapter())
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    svc.validate_session(session.session_id)
    report = svc.get_repeatability_report(session.session_id)
    assert report.validation_passed is False
    assert report.repeatability_score < 100


# ═══════════════════════════════════════════════════════════════════════════════
# POST-READY WORKFLOW — Activate → Active → Reset → Reclaim
# ═══════════════════════════════════════════════════════════════════════════════


def _provision_to_ready(svc=None):
    if svc is None:
        svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    session = svc.validate_session(session.session_id)
    assert session.status == SessionStatus.READY
    return svc, session


# ─── STEP 19: Activate ready session ─────────────────────────────────────────

def test_activate_ready_session():
    svc, session = _provision_to_ready()
    activated = svc.activate_session(session.session_id)
    assert activated.status == SessionStatus.ACTIVE
    assert activated.started_at is not None


def test_activate_raises_for_non_ready_session():
    svc = ProvisioningService()
    req = svc.submit_request(_make_request())
    session = svc.provision(req.request_id)
    with pytest.raises(Exception):
        svc.activate_session(session.session_id)


# ─── STEP 20: Activate raises for missing session ────────────────────────────

def test_activate_finds_existing_session():
    svc, session = _provision_to_ready()
    activated = svc.activate_session(session.session_id)
    assert activated.session_id == session.session_id


def test_activate_raises_for_missing_session():
    svc = ProvisioningService()
    with pytest.raises(ValueError, match="not found"):
        svc.activate_session("nonexistent-session-id")


# ─── STEP 21: Reset active session ───────────────────────────────────────────

def test_reset_active_session():
    svc, session = _provision_to_ready()
    activated = svc.activate_session(session.session_id)
    reset = svc.reset_session(activated.session_id)
    assert reset.status == SessionStatus.RESETTING


def test_reset_raises_for_non_active_session():
    svc, session = _provision_to_ready()
    with pytest.raises(Exception):
        svc.reset_session(session.session_id)


# ─── STEP 22: Reclaim resetting session ──────────────────────────────────────

def test_reclaim_resetting_session():
    svc, session = _provision_to_ready()
    activated = svc.activate_session(session.session_id)
    reset = svc.reset_session(activated.session_id)
    reclaimed = svc.reclaim_session(reset.session_id)
    assert reclaimed.status == SessionStatus.RECLAIMED
    assert reclaimed.completed_at is not None


def test_reclaim_raises_for_missing_session():
    svc = ProvisioningService()
    with pytest.raises(ValueError, match="not found"):
        svc.reclaim_session("nonexistent-session-id")


# ─── STEP 23: Full post-ready lifecycle ───────────────────────────────────────

def test_full_post_ready_lifecycle():
    svc, session = _provision_to_ready()
    session = svc.activate_session(session.session_id)
    assert session.status == SessionStatus.ACTIVE
    assert session.started_at is not None

    session = svc.reset_session(session.session_id)
    assert session.status == SessionStatus.RESETTING

    session = svc.reclaim_session(session.session_id)
    assert session.status == SessionStatus.RECLAIMED
    assert session.completed_at is not None

    events = session.lifecycle_events
    statuses = [(e.from_status, e.to_status) for e in events]
    assert (SessionStatus.READY, SessionStatus.ACTIVE) in statuses
    assert (SessionStatus.ACTIVE, SessionStatus.RESETTING) in statuses
    assert (SessionStatus.RESETTING, SessionStatus.RECLAIMED) in statuses


def test_full_post_ready_lifecycle_cannot_reactivate():
    svc, session = _provision_to_ready()
    session = svc.activate_session(session.session_id)
    session = svc.reset_session(session.session_id)
    session = svc.reclaim_session(session.session_id)
    with pytest.raises(Exception):
        svc.activate_session(session.session_id)


# ─── STEP 24: API full post-ready workflow ────────────────────────────────────

def test_api_full_post_ready_workflow():
    from fastapi.testclient import TestClient
    from app.api.deps import provisioning_service
    from app.main import app

    provisioning_service._requests.clear()
    provisioning_service._sessions.clear()
    provisioning_service._plans.clear()

    client = TestClient(app)

    req_payload = {
        "tenant_id": "partner-oem-a",
        "requester_id": "demo-engineer-1",
        "catalog_item_id": "inference-overdrive-quickstart",
        "requested_mode": "quick_start",
        "persistence": "ephemeral",
        "ttl": "4h",
    }

    resp = client.post("/lab-requests", json=req_payload)
    request_id = resp.json()["request_id"]

    resp = client.post(f"/lab-requests/{request_id}/provision")
    session_id = resp.json()["session_id"]

    resp = client.post(f"/lab-sessions/{session_id}/validate")
    assert resp.json()["status"] == "ready"

    resp = client.post(f"/lab-sessions/{session_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["started_at"] is not None

    resp = client.post(f"/lab-sessions/{session_id}/reset")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resetting"

    resp = client.post(f"/lab-sessions/{session_id}/reclaim")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reclaimed"
    assert resp.json()["completed_at"] is not None


def test_api_activate_wrong_status_returns_400():
    from fastapi.testclient import TestClient
    from app.api.deps import provisioning_service
    from app.main import app

    provisioning_service._requests.clear()
    provisioning_service._sessions.clear()
    provisioning_service._plans.clear()

    client = TestClient(app)

    req_payload = {
        "tenant_id": "partner-oem-a",
        "requester_id": "demo-engineer-1",
        "catalog_item_id": "inference-overdrive-quickstart",
        "requested_mode": "quick_start",
    }

    resp = client.post("/lab-requests", json=req_payload)
    request_id = resp.json()["request_id"]
    resp = client.post(f"/lab-requests/{request_id}/provision")
    session_id = resp.json()["session_id"]

    resp = client.post(f"/lab-sessions/{session_id}/activate")
    assert resp.status_code == 400
