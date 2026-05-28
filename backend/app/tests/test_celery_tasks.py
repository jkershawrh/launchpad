"""Celery task infrastructure — TDD red/green.

Tests that lifecycle tasks are importable, correctly decorated,
and invoke the right provisioning service methods.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Module & import tests
# ---------------------------------------------------------------------------

class TestCeleryAppExists:
    """Celery application is importable and correctly configured."""

    def test_celery_app_importable(self):
        from celery_app import app
        assert app is not None

    def test_celery_app_name(self):
        from celery_app import app
        assert app.main == "launchpad"

    def test_redis_broker_url_uses_db2(self):
        from celery_app import REDIS_URL
        assert "/2" in REDIS_URL

    def test_broker_uses_ecosystem_redis(self):
        from celery_app import REDIS_URL
        assert "ecosystem-redis" in REDIS_URL

    def test_json_serializer(self):
        from celery_app import app
        assert app.conf.task_serializer == "json"

    def test_utc_enabled(self):
        from celery_app import app
        assert app.conf.enable_utc is True

    def test_acks_late(self):
        from celery_app import app
        assert app.conf.task_acks_late is True


class TestBeatSchedule:
    """Beat schedule has the expected periodic tasks."""

    def test_ttl_enforcement_in_schedule(self):
        from celery_app import app
        assert "ttl-enforcement" in app.conf.beat_schedule

    def test_ttl_enforcement_interval(self):
        from celery_app import app
        entry = app.conf.beat_schedule["ttl-enforcement"]
        assert entry["schedule"] == 300.0

    def test_ttl_enforcement_task_path(self):
        from celery_app import app
        entry = app.conf.beat_schedule["ttl-enforcement"]
        assert entry["task"] == "tasks.lifecycle.enforce_ttl"

    def test_session_cleanup_in_schedule(self):
        from celery_app import app
        assert "session-cleanup" in app.conf.beat_schedule

    def test_session_cleanup_interval(self):
        from celery_app import app
        entry = app.conf.beat_schedule["session-cleanup"]
        assert entry["schedule"] == 3600.0

    def test_session_cleanup_task_path(self):
        from celery_app import app
        entry = app.conf.beat_schedule["session-cleanup"]
        assert entry["task"] == "tasks.lifecycle.reclaim_session"


# ---------------------------------------------------------------------------
# 2. Task registration tests
# ---------------------------------------------------------------------------

class TestTasksImportable:
    """Lifecycle tasks are importable and registered as shared_tasks."""

    def test_enforce_ttl_importable(self):
        from tasks.lifecycle import enforce_ttl
        assert callable(enforce_ttl)

    def test_reclaim_session_importable(self):
        from tasks.lifecycle import reclaim_session
        assert callable(reclaim_session)

    def test_publish_event_importable(self):
        from tasks.lifecycle import publish_event
        assert callable(publish_event)

    def test_enforce_ttl_is_celery_task(self):
        from tasks.lifecycle import enforce_ttl
        # shared_task-decorated functions have a .delay method
        assert hasattr(enforce_ttl, "delay")

    def test_reclaim_session_is_celery_task(self):
        from tasks.lifecycle import reclaim_session
        assert hasattr(reclaim_session, "delay")

    def test_publish_event_is_celery_task(self):
        from tasks.lifecycle import publish_event
        assert hasattr(publish_event, "delay")


# ---------------------------------------------------------------------------
# 3. enforce_ttl task logic
# ---------------------------------------------------------------------------

class TestEnforceTTLTask:
    """enforce_ttl delegates to provisioning_service.enforce_ttl()."""

    @patch("tasks.lifecycle.provisioning_service", create=True)
    def test_calls_provisioning_enforce_ttl(self, _mock):
        # We need to patch at the import location inside the task
        with patch("app.api.deps.provisioning_service") as mock_svc:
            mock_svc.enforce_ttl.return_value = 3
            from tasks.lifecycle import enforce_ttl
            result = enforce_ttl()
            mock_svc.enforce_ttl.assert_called_once()
            assert result["status"] == "ok"
            assert result["reclaimed"] == 3

    def test_returns_error_on_exception(self):
        with patch("app.api.deps.provisioning_service") as mock_svc:
            mock_svc.enforce_ttl.side_effect = RuntimeError("db down")
            from tasks.lifecycle import enforce_ttl
            result = enforce_ttl()
            assert result["status"] == "error"
            assert "db down" in result["error"]


# ---------------------------------------------------------------------------
# 4. reclaim_session task logic
# ---------------------------------------------------------------------------

class TestReclaimSessionTask:
    """reclaim_session handles both targeted and orphan-scan modes."""

    def test_targeted_reclaim_calls_service(self):
        with patch("app.api.deps.provisioning_service") as mock_svc:
            from tasks.lifecycle import reclaim_session
            result = reclaim_session(session_id="sess-001")
            mock_svc.reclaim_session.assert_called_once_with("sess-001")
            assert result["status"] == "ok"
            assert result["session_id"] == "sess-001"

    def test_orphan_scan_reclaims_stuck_sessions(self):
        """Sessions stuck in provisioning for > 30 min get force-reclaimed."""
        mock_session = MagicMock()
        mock_session.session_id = "orphan-001"
        mock_session.status.value = "provisioning"
        mock_session.lifecycle_events = []
        mock_session.created_at = datetime.utcnow() - timedelta(hours=2)

        with patch("app.api.deps.provisioning_service") as mock_svc:
            mock_svc._sessions = {"orphan-001": mock_session}
            from tasks.lifecycle import reclaim_session
            result = reclaim_session()
            mock_svc.force_reclaim_session.assert_called_once_with("orphan-001")
            assert result["status"] == "ok"
            assert "orphan-001" in result["reclaimed"]

    def test_orphan_scan_skips_recent_sessions(self):
        """Sessions in transitional state for < 30 min are left alone."""
        mock_session = MagicMock()
        mock_session.session_id = "recent-001"
        mock_session.status.value = "provisioning"
        mock_session.lifecycle_events = []
        mock_session.created_at = datetime.utcnow() - timedelta(minutes=5)

        with patch("app.api.deps.provisioning_service") as mock_svc:
            mock_svc._sessions = {"recent-001": mock_session}
            from tasks.lifecycle import reclaim_session
            result = reclaim_session()
            mock_svc.force_reclaim_session.assert_not_called()
            assert result["reclaimed"] == []

    def test_orphan_scan_skips_active_sessions(self):
        """Sessions in stable states (active, ready) are not orphans."""
        mock_session = MagicMock()
        mock_session.session_id = "active-001"
        mock_session.status.value = "active"
        mock_session.lifecycle_events = []
        mock_session.created_at = datetime.utcnow() - timedelta(hours=2)

        with patch("app.api.deps.provisioning_service") as mock_svc:
            mock_svc._sessions = {"active-001": mock_session}
            from tasks.lifecycle import reclaim_session
            result = reclaim_session()
            mock_svc.force_reclaim_session.assert_not_called()

    def test_returns_error_on_exception(self):
        with patch("app.api.deps.provisioning_service") as mock_svc:
            mock_svc.reclaim_session.side_effect = RuntimeError("boom")
            from tasks.lifecycle import reclaim_session
            result = reclaim_session(session_id="sess-fail")
            assert result["status"] == "error"


# ---------------------------------------------------------------------------
# 5. publish_event task logic
# ---------------------------------------------------------------------------

class TestPublishEventTask:
    """publish_event wraps event_publisher.publish_event."""

    def test_delegates_to_event_publisher(self):
        with patch("app.integrations.event_publisher.publish_event") as mock_pub:
            from tasks.lifecycle import publish_event
            result = publish_event(
                session_id="sess-001",
                namespace="lab-partner-001",
                status="active",
                lab_code="inference-overdrive",
                tenant_id="partner-oem-a",
            )
            mock_pub.assert_called_once_with(
                session_id="sess-001",
                namespace="lab-partner-001",
                status="active",
                lab_code="inference-overdrive",
                tenant_id="partner-oem-a",
                error_summary="",
                resources={},
            )
            assert result["status"] == "ok"
            assert result["event"] == "session.active"

    def test_passes_error_summary(self):
        with patch("app.integrations.event_publisher.publish_event") as mock_pub:
            from tasks.lifecycle import publish_event
            result = publish_event(
                session_id="sess-002",
                namespace="lab-ns",
                status="cleanup_failed",
                error_summary="ns delete timeout",
            )
            call_kwargs = mock_pub.call_args[1]
            assert call_kwargs["error_summary"] == "ns delete timeout"

    def test_returns_error_on_exception(self):
        with patch("app.integrations.event_publisher.publish_event",
                    side_effect=RuntimeError("network")):
            from tasks.lifecycle import publish_event
            result = publish_event(
                session_id="sess-003",
                namespace="ns",
                status="active",
            )
            assert result["status"] == "error"
            assert "network" in result["error"]


# ---------------------------------------------------------------------------
# 6. Tasks module __init__ is importable
# ---------------------------------------------------------------------------

class TestTasksPackage:
    """tasks package is a proper Python package."""

    def test_tasks_init_importable(self):
        import tasks
        assert tasks is not None
