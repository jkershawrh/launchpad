"""Fleet enrichment task — pull historical data from StarGate + DeepField every 5 min."""

import logging

from celery import shared_task

logger = logging.getLogger("launchpad.tasks.fleet_enrichment")


@shared_task(bind=True, max_retries=1)
def refresh_fleet_enrichment(self):
    """Pull deeper operational data from StarGate and DeepField.

    Runs every 300s via beat. Read-only, cached locally.
    """
    try:
        from app.api.deps import get_fleet_enrichment

        enrichment = get_fleet_enrichment()
        if not enrichment:
            return {"status": "skipped", "reason": "no enrichment service"}

        counts = enrichment.refresh()
        logger.info("Fleet enrichment: %s", counts)
        return {"status": "ok", **counts}
    except Exception as e:
        logger.warning("Fleet enrichment failed: %s", e)
        return {"status": "error", "error": str(e)}
