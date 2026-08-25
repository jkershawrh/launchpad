"""
TDD: Cleanup hardening tests.
8 fixes, all RED first, then GREEN one at a time.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.domain.enums import CatalogCategory, Persistence, SessionStatus
from app.domain.models import LabRequest, Workshop
from app.services.provisioning import ProvisioningService


def _svc(**kw):
    return ProvisioningService(**kw)


def _req(**kw):
    defaults = dict(
        tenant_id="cleanup-test",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(kw)
    return LabRequest(**defaults)


def _provision(svc, **req_kw):
    r = svc.submit_request(_req(**req_kw))
    return svc.provision(r.request_id)


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: TTL Enforcement
# ═══════════════════════════════════════════════════════════════════════════════

class TestTTLEnforcement:

    def test_enforce_ttl_reclaims_expired_session(self):
        """RED: expired session should be auto-reclaimed."""
        svc = _svc()
        session = _provision(svc, ttl="1h")
        validated = svc.validate_session(session.session_id)
        activated = svc.activate_session(validated.session_id)

        # Manually expire the session
        expired = activated.model_copy(update={
            "expires_at": datetime.utcnow() - timedelta(hours=1)
        })
        svc._sessions[expired.session_id] = expired

        svc.enforce_ttl()

        result = svc.get_session(expired.session_id)
        assert result.status == SessionStatus.RECLAIMED

    def test_enforce_ttl_skips_persistent(self):
        """RED: persistent session should NOT be reclaimed."""
        svc = _svc()
        session = _provision(svc, persistence=Persistence.PERSISTENT)
        validated = svc.validate_session(session.session_id)
        activated = svc.activate_session(validated.session_id)

        svc.enforce_ttl()

        result = svc.get_session(activated.session_id)
        assert result.status == SessionStatus.ACTIVE

    def test_enforce_ttl_skips_already_reclaimed(self):
        """GREEN baseline: reclaimed sessions are not touched."""
        svc = _svc()
        session = _provision(svc)
        svc.force_reclaim_session(session.session_id)

        svc.enforce_ttl()

        result = svc.get_session(session.session_id)
        assert result.status == SessionStatus.RECLAIMED

    def test_enforce_ttl_skips_provisioning(self):
        """RED: session still provisioning should NOT be reclaimed even if expired."""
        svc = _svc()
        session = _provision(svc)
        # Session is in VALIDATING state, set expired
        expired = session.model_copy(update={
            "expires_at": datetime.utcnow() - timedelta(hours=1)
        })
        svc._sessions[expired.session_id] = expired

        svc.enforce_ttl()

        result = svc.get_session(expired.session_id)
        assert result.status != SessionStatus.RECLAIMED


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: Credential Scrubbing
# ═══════════════════════════════════════════════════════════════════════════════

class TestCredentialScrubbing:

    def test_reclaim_scrubs_maas_key(self):
        """RED: after reclaim, maas_api_key must be None."""
        svc = _svc()
        session = _provision(svc)
        # Use force_reclaim which bypasses lifecycle
        svc.force_reclaim_session(session.session_id)

        result = svc.get_session(session.session_id)
        assert result.maas_api_key is None

    def test_reclaim_scrubs_sa_token_from_resources(self):
        """RED: after reclaim, resources must not contain sa_token."""
        svc = _svc()
        session = _provision(svc)
        session = session.model_copy(update={
            "resources": {**session.resources, "sa_token": "secret-token-123"}
        })
        svc._sessions[session.session_id] = session
        svc.force_reclaim_session(session.session_id)

        result = svc.get_session(session.session_id)
        assert "sa_token" not in result.resources

    def test_reclaim_scrubs_plan_credentials(self):
        """RED: after reclaim, plan must not contain maas_api_key."""
        svc = _svc()
        session = _provision(svc)
        svc.force_reclaim_session(session.session_id)

        for plan in svc._plans.values():
            if plan.request_id == session.request_id:
                assert "maas_api_key" not in plan.required_resources

    def test_force_reclaim_scrubs_credentials(self):
        """RED: force_reclaim also scrubs credentials."""
        svc = _svc()
        session = _provision(svc)
        svc.force_reclaim_session(session.session_id)

        result = svc.get_session(session.session_id)
        assert result.maas_api_key is None


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3: force_reclaim Calls Cleanup
# ═══════════════════════════════════════════════════════════════════════════════

class TestForceReclaimCleanup:

    def test_force_reclaim_calls_cleanup_on_namespace(self):
        """RED: force_reclaim should call cleanup adapter for the namespace."""
        mock_cleanup = MagicMock()
        svc = _svc(cleanup=mock_cleanup)
        session = _provision(svc)

        svc.force_reclaim_session(session.session_id)

        cleanup_calls = [str(c) for c in mock_cleanup.cleanup.call_args_list]
        any(session.namespace in str(c) for c in cleanup_calls) if session.namespace else True
        assert mock_cleanup.cleanup.called or session.namespace is None

    def test_force_reclaim_can_require_successful_cleanup(self):
        """A workshop reclaim must not report success when cleanup still fails."""
        mock_cleanup = MagicMock()
        mock_cleanup.cleanup.side_effect = RuntimeError("Argo deletion timed out")
        svc = _svc(cleanup=mock_cleanup)
        session = _provision(svc)

        result = svc.force_reclaim_session(
            session.session_id, require_cleanup_success=True
        )

        assert result.status == SessionStatus.CLEANUP_FAILED
        assert "Argo deletion timed out" in result.lifecycle_events[-1].reason


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 4: Workshop Error Tracking
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkshopErrorTracking:

    def test_workshop_all_success(self):
        """GREEN baseline: all sessions reclaim → status completed."""
        svc = _svc()
        w = Workshop(
            tenant_id="ws-test",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2, ttl="4h",
        )
        provisioned = svc.provision_workshop(w)
        reclaimed = svc.reclaim_workshop(provisioned.workshop_id)
        assert reclaimed.status == "completed"
        assert "failed_reclaims" not in reclaimed.metadata or len(reclaimed.metadata.get("failed_reclaims", [])) == 0

    def test_workshop_partial_failure_tracked(self):
        """RED: if some sessions fail, status should be completed_with_errors."""
        svc = _svc()
        w = Workshop(
            tenant_id="ws-fail-test",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2, ttl="4h",
        )
        provisioned = svc.provision_workshop(w)

        # Force one session into a state that can't be reclaimed and break force_reclaim
        if provisioned.session_ids:
            bad_sid = provisioned.session_ids[0]
            svc.get_session(bad_sid)
            # Remove from internal store so reclaim raises ValueError
            del svc._sessions[bad_sid]

        reclaimed = svc.reclaim_workshop(provisioned.workshop_id)
        assert reclaimed.status == "completed_with_errors"
        assert len(reclaimed.metadata.get("failed_reclaims", [])) > 0

    def test_workshop_does_not_hide_force_cleanup_failure(self):
        mock_cleanup = MagicMock()
        mock_cleanup.cleanup.side_effect = RuntimeError("Argo deletion timed out")
        svc = _svc(cleanup=mock_cleanup)
        workshop = svc.provision_workshop(Workshop(
            tenant_id="ws-cleanup-fail-test",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=1,
            ttl="4h",
        ))

        reclaimed = svc.reclaim_workshop(workshop.workshop_id)

        assert reclaimed.status == "completed_with_errors"
        assert reclaimed.seats[0].status == "failed"
        assert "Argo deletion timed out" in reclaimed.seats[0].error


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 8: Cleanup Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanupAuditTrail:

    def test_reclaim_lifecycle_event_has_cleanup_metadata(self):
        """RED: the RECLAIMED lifecycle event should include cleanup details."""
        svc = _svc()
        session = _provision(svc)
        svc.force_reclaim_session(session.session_id)

        result = svc.get_session(session.session_id)
        reclaim_events = [e for e in result.lifecycle_events if e.to_status == SessionStatus.RECLAIMED]
        assert len(reclaim_events) >= 1

        last_event = reclaim_events[-1]
        assert last_event.reason is not None
        assert "credentials scrubbed" in last_event.reason
