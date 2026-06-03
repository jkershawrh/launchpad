"""Capacity sync task — refresh cluster capacity cache from StarGate."""

import logging

from celery import shared_task

logger = logging.getLogger("launchpad.tasks.capacity_sync")


@shared_task(bind=True, max_retries=1)
def sync_cluster_capacity(self):
    """Refresh the PlacementService capacity cache from StarGate.

    Runs every 60s via beat. Non-critical — if StarGate is down,
    the cache keeps its previous values until the next successful refresh.
    """
    try:
        from app.api.deps import get_placement_service

        placement = get_placement_service()
        if not placement:
            return {"status": "skipped", "reason": "no placement service configured"}

        count = placement.refresh_capacity_cache()
        logger.info("Capacity sync: refreshed %d clusters", count)
        return {"status": "ok", "clusters": count}
    except Exception as e:
        logger.warning("Capacity sync failed: %s", e)
        return {"status": "error", "error": str(e)}
