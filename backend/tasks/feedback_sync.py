"""Feedback sync task — refresh in-memory aggregates from database."""

import logging

from celery import shared_task

logger = logging.getLogger("launchpad.tasks.feedback_sync")


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def refresh_feedback_aggregates(self):
    """Reload feedback outcomes from PostgreSQL into the in-memory tracker.

    Runs every 300s via beat. Ensures the FeedbackTracker has fresh data
    if outcomes were recorded by other worker processes.
    """
    try:
        from app.api.deps import get_feedback_tracker

        tracker = get_feedback_tracker()
        if not tracker:
            return {"status": "skipped", "reason": "no feedback tracker configured"}

        db = getattr(tracker, "_db", None)
        if not db:
            return {"status": "skipped", "reason": "no database store configured"}

        outcomes = db.list_all()
        tracker._outcomes = outcomes
        logger.info("Feedback sync: loaded %d outcomes from database", len(outcomes))
        return {"status": "ok", "outcomes": len(outcomes)}
    except Exception as e:
        logger.warning("Feedback sync failed (retry %d/%d): %s", self.request.retries, self.max_retries, e)
        raise self.retry(exc=e)
