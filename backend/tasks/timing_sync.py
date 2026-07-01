"""Timing sync task — refresh provisioning timing cache from Babylon every 10 min."""

import logging

from celery import shared_task

logger = logging.getLogger("launchpad.tasks.timing_sync")


@shared_task(bind=True, max_retries=3, retry_backoff=True, soft_time_limit=120)
def refresh_provisioning_timing(self):
    """Pull provisioning timing from Babylon AnarchySubjects.

    Runs every 600s via beat. Heavy operation (29 namespaces) so
    runs in background, not per-request.
    """
    try:
        from app.api.routers.intelligence import _get_timing

        svc = _get_timing()
        if not svc:
            return {"status": "skipped", "reason": "no timing service"}

        count = svc.refresh()
        logger.info("Timing sync: %d provisions", count)
        return {"status": "ok", "provisions": count}
    except Exception as e:
        logger.warning("Timing sync failed: %s", e)
        return {"status": "error", "error": str(e)}
