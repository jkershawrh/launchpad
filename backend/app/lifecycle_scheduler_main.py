from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from app.storage.database import get_database_url, init_db

logger = logging.getLogger("launchpad.lifecycle-scheduler")


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if os.environ.get("LIFECYCLE_HA_ENABLED", "false").lower() != "true":
        logger.info("LIFECYCLE_HA_ENABLED is false; no system jobs enqueued")
        return 0
    if os.environ.get("LAUNCHPAD_CONTROL_PLANE_ROLE", "active").lower() != "active":
        logger.error("Control plane is not active; no system jobs enqueued")
        return 2
    if not get_database_url():
        logger.error("DATABASE_URL is required; refusing in-memory scheduling")
        return 2
    if not asyncio.run(init_db()):
        logger.error("PostgreSQL initialization failed; no system jobs enqueued")
        return 2

    from app.api.deps import lifecycle_queue_service

    cycle_id = datetime.now(UTC).strftime("%Y%m%dT%H%M")
    ttl = lifecycle_queue_service.enqueue_ttl_cycle(cycle_id)
    reconcile = lifecycle_queue_service.enqueue_reconciliation_cycle(cycle_id)
    logger.info(
        "Enqueued lifecycle cycles ttl=%s reconcile=%s cycle=%s",
        ttl.job_id,
        reconcile.job_id,
        cycle_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
