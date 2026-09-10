from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import threading
import uuid

from app.storage.database import get_database_url, init_db

logger = logging.getLogger("launchpad.lifecycle-worker")


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if os.environ.get("LIFECYCLE_HA_ENABLED", "false").lower() != "true":
        logger.error("LIFECYCLE_HA_ENABLED is false; refusing to start worker")
        return 2
    if os.environ.get("LAUNCHPAD_CONTROL_PLANE_ROLE", "active").lower() != "active":
        logger.error("Control plane is not active; refusing to start worker")
        return 2
    if not get_database_url():
        logger.error("DATABASE_URL is required; refusing in-memory lifecycle work")
        return 2
    if not asyncio.run(init_db()):
        logger.error("PostgreSQL initialization failed; refusing to start worker")
        return 2

    # Import after migrations so the singleton provisioning service can load
    # only schemas that are known to exist.
    from app.api.deps import lifecycle_job_store, provisioning_service
    from app.services.lifecycle_worker import LifecycleWorker

    worker_id = os.environ.get(
        "LIFECYCLE_WORKER_ID",
        f"{socket.gethostname()}-{str(uuid.uuid4())[:8]}",
    )
    lease_seconds = int(os.environ.get("LIFECYCLE_JOB_LEASE_SECONDS", "120"))
    heartbeat_seconds = int(
        os.environ.get("LIFECYCLE_HEARTBEAT_INTERVAL_SECONDS", "15")
    )
    poll_seconds = float(os.environ.get("LIFECYCLE_POLL_INTERVAL_SECONDS", "2"))
    serialize_workshop_provisioning = (
        os.environ.get("SERIALIZE_WORKSHOP_PROVISIONING", "true").lower() == "true"
    )
    stop = threading.Event()

    def request_stop(*_args) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker = LifecycleWorker(
        store=lifecycle_job_store,
        provisioning_service=provisioning_service,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        heartbeat_interval_seconds=heartbeat_seconds,
        serialize_workshop_provisioning=serialize_workshop_provisioning,
    )
    logger.info(
        "Lifecycle worker %s started (serialize_workshop_provisioning=%s)",
        worker_id,
        serialize_workshop_provisioning,
    )
    while not stop.is_set():
        result = worker.run_once()
        if result == "idle":
            stop.wait(poll_seconds)
    logger.info("Lifecycle worker %s stopped", worker_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
