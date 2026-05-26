"""
TDD: StarGate ↔ Launchpad integration tests.
Callback endpoint, pre-flight checks, cleanup delegation.
"""
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.domain.enums import CatalogCategory, SessionStatus
from app.domain.models import LabRequest
from app.main import app
from app.services.provisioning import ProvisioningService

client = TestClient(app)


def _svc(**kw):
    return ProvisioningService(**kw)


def _req(**kw):
    defaults = dict(
        tenant_id="sg-test",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(kw)
    return LabRequest(**defaults)


def _provision(svc, **kw):
    r = svc.submit_request(_req(**kw))
    return svc.provision(r.request_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Callback Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanupCallback:

    def test_callback_endpoint_exists(self):
        """RED: POST /callbacks/cleanup-result should exist and accept valid payloads."""
        resp = client.post("/api/v1/callbacks/cleanup-result", json={
            "session_id": "nonexistent",
            "result": "success",
        })
        assert resp.status_code in (200, 404), "Callback endpoint should exist (404 = session not found, not route missing)"
        assert "Session" in resp.json().get("detail", "") or resp.status_code == 200

    def test_callback_finalizes_cleanup_failed_session(self):
        """RED: callback with success should transition CLEANUP_FAILED → RECLAIMED."""
        from app.api.deps import provisioning_service
        session = _provision(provisioning_service)

        # Manually set to CLEANUP_FAILED
        from app.domain.models import LifecycleEvent
        event = LifecycleEvent(
            from_status=session.status,
            to_status=SessionStatus.CLEANUP_FAILED,
            reason="test cleanup failure",
        )
        failed = session.model_copy(update={
            "status": SessionStatus.CLEANUP_FAILED,
            "lifecycle_events": session.lifecycle_events + [event],
        })
        provisioning_service._sessions[failed.session_id] = failed

        resp = client.post("/api/v1/callbacks/cleanup-result", json={
            "session_id": failed.session_id,
            "result": "success",
            "namespace_deleted": True,
            "placement_released": True,
        })
        assert resp.status_code == 200

        result = provisioning_service.get_session(failed.session_id)
        assert result.status == SessionStatus.RECLAIMED

    def test_callback_with_failure_keeps_cleanup_failed(self):
        """RED: callback with failure should keep session in CLEANUP_FAILED."""
        from app.api.deps import provisioning_service
        session = _provision(provisioning_service)

        from app.domain.models import LifecycleEvent
        event = LifecycleEvent(
            from_status=session.status,
            to_status=SessionStatus.CLEANUP_FAILED,
            reason="test cleanup failure",
        )
        failed = session.model_copy(update={
            "status": SessionStatus.CLEANUP_FAILED,
            "lifecycle_events": session.lifecycle_events + [event],
        })
        provisioning_service._sessions[failed.session_id] = failed

        resp = client.post("/api/v1/callbacks/cleanup-result", json={
            "session_id": failed.session_id,
            "result": "failure",
            "errors": ["namespace stuck in Terminating"],
        })
        assert resp.status_code == 200

        result = provisioning_service.get_session(failed.session_id)
        assert result.status == SessionStatus.CLEANUP_FAILED


# ═══════════════════════════════════════════════════════════════════════════════
# Pre-flight Check (StarGate as ConstraintAdapter)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreflightCheck:

    def test_stargate_constraint_adapter_exists(self):
        """RED: StarGateConstraintAdapter should be importable."""
        from app.adapters.stargate.constraints import StarGateConstraintAdapter
        adapter = StarGateConstraintAdapter(api_url="https://stargate.test")
        assert adapter is not None

    def test_stargate_constraint_blocks_unhealthy_cluster(self):
        """RED: if StarGate says blocked, constraint returns not allowed."""
        from app.adapters.stargate.constraints import StarGateConstraintAdapter
        adapter = StarGateConstraintAdapter(api_url="https://stargate.test")

        with patch("app.adapters.stargate.constraints.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "allowed": False,
                    "level": "blocked",
                    "reasons": ["cluster unhealthy: 3 pods crashlooping"],
                }),
            )
            result = adapter.evaluate(_req())
            assert not result.allowed
            assert "unhealthy" in result.reasons[0]

    def test_stargate_constraint_allows_healthy_cluster(self):
        """RED: if StarGate says allowed, constraint returns allowed."""
        from app.adapters.stargate.constraints import StarGateConstraintAdapter
        adapter = StarGateConstraintAdapter(api_url="https://stargate.test")

        with patch("app.adapters.stargate.constraints.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "allowed": True,
                    "level": "allowed",
                    "reasons": [],
                }),
            )
            result = adapter.evaluate(_req())
            assert result.allowed

    def test_stargate_down_falls_back_to_allowed(self):
        """RED: if StarGate is unreachable, fall back to allowed."""
        from app.adapters.stargate.constraints import StarGateConstraintAdapter
        adapter = StarGateConstraintAdapter(api_url="https://stargate.test")

        with patch("app.adapters.stargate.constraints.requests.get") as mock_get:
            mock_get.side_effect = Exception("connection refused")
            result = adapter.evaluate(_req())
            assert result.allowed
