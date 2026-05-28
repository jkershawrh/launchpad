"""Lifecycle tasks — TTL enforcement, orphan session cleanup, event publishing."""

import logging
from datetime import datetime

from celery import shared_task

logger = logging.getLogger("launchpad.tasks.lifecycle")


@shared_task(bind=True, max_retries=1)
def enforce_ttl(self):
    """Reclaim sessions whose TTL has expired.

    Runs every 300s via beat. Delegates to ProvisioningService.enforce_ttl()
    which iterates active/ready sessions and reclaims any past their expires_at.
    """
    try:
        from app.api.deps import provisioning_service

        reclaimed = provisioning_service.enforce_ttl()
        logger.info("TTL enforcement: reclaimed %d expired sessions", reclaimed)
        return {"status": "ok", "reclaimed": reclaimed}
    except Exception as e:
        logger.warning("TTL enforcement failed: %s", e)
        return {"status": "error", "error": str(e)}


@shared_task(bind=True, max_retries=1, soft_time_limit=600)
def reclaim_session(self, session_id=None):
    """Reclaim a specific session, or find and reclaim orphaned sessions.

    When called by beat (no session_id): scans for orphaned sessions —
    sessions stuck in transitional states (provisioning, resetting, validating)
    for longer than 30 minutes without progress.

    When called with a session_id: reclaims that specific session.
    """
    try:
        from app.api.deps import provisioning_service

        if session_id:
            provisioning_service.reclaim_session(session_id)
            logger.info("Reclaimed session %s", session_id)
            return {"status": "ok", "session_id": session_id}

        # Orphan scan: find sessions stuck in transitional states
        now = datetime.utcnow()
        orphan_states = {"provisioning", "resetting", "validating"}
        orphan_timeout_seconds = 1800  # 30 minutes
        reclaimed = []

        for session in list(provisioning_service._sessions.values()):
            if session.status.value not in orphan_states:
                continue
            # Check if session has been in transitional state too long
            last_event_time = (
                session.lifecycle_events[-1].timestamp
                if session.lifecycle_events
                else session.created_at
            )
            if last_event_time and (now - last_event_time).total_seconds() > orphan_timeout_seconds:
                try:
                    provisioning_service.force_reclaim_session(session.session_id)
                    reclaimed.append(session.session_id)
                    logger.info("Reclaimed orphaned session %s (stuck in %s)",
                                session.session_id, session.status.value)
                except Exception as e:
                    logger.warning("Failed to reclaim orphan %s: %s",
                                   session.session_id, e)

        logger.info("Orphan scan: reclaimed %d orphaned sessions", len(reclaimed))
        return {"status": "ok", "reclaimed": reclaimed}
    except Exception as e:
        logger.warning("Session reclaim failed: %s", e)
        return {"status": "error", "error": str(e)}


@shared_task
def publish_event(session_id, namespace, status, lab_code="", tenant_id="",
                  error_summary="", resources=None):
    """Publish a lifecycle event to all configured integration targets.

    Wraps the existing event_publisher.publish_event() so callers can fire
    and forget via Celery instead of blocking the request thread.
    """
    try:
        from app.integrations.event_publisher import publish_event as _publish

        _publish(
            session_id=session_id,
            namespace=namespace,
            status=status,
            lab_code=lab_code,
            tenant_id=tenant_id,
            error_summary=error_summary,
            resources=resources or {},
        )
        logger.info("Published event session.%s for %s", status, session_id)
        return {"status": "ok", "event": f"session.{status}"}
    except Exception as e:
        logger.warning("Event publish failed: %s", e)
        return {"status": "error", "error": str(e)}
