"""Orchestration tasks — rebalance check and proactive health monitoring."""

import logging

from celery import shared_task

logger = logging.getLogger("launchpad.tasks.orchestration")


@shared_task(bind=True, max_retries=1)
def run_proactive_health(self):
    """Check fleet health via OrchestrationBrain and log alerts.

    Runs every 120s via beat. Non-critical — if brain or DeepField
    is unavailable, returns empty.
    """
    try:
        from app.api.deps import get_brain

        brain = get_brain()
        if not brain:
            return {"status": "skipped", "reason": "no brain configured"}

        alerts = brain.proactive_health_check()
        if alerts:
            for alert in alerts:
                logger.warning("Health alert: %s on %s — %s",
                               alert.severity, alert.cluster_name, alert.recommended_action)

        return {"status": "ok", "alerts": len(alerts)}
    except Exception as e:
        logger.warning("Proactive health check failed: %s", e)
        return {"status": "error", "error": str(e)}


@shared_task(bind=True, max_retries=1)
def run_rebalance_check(self):
    """Check for overloaded clusters and suggest session migrations.

    Runs every 600s via beat. Non-critical — advisory only.
    """
    try:
        from app.api.deps import get_brain

        brain = get_brain()
        if not brain:
            return {"status": "skipped", "reason": "no brain configured"}

        actions = brain.rebalance_check()
        if actions:
            for action in actions:
                logger.info("Rebalance suggestion: move %s from %s (%s)",
                            action.session_id, action.from_cluster, action.reason)

        return {"status": "ok", "suggestions": len(actions)}
    except Exception as e:
        logger.warning("Rebalance check failed: %s", e)
        return {"status": "error", "error": str(e)}
