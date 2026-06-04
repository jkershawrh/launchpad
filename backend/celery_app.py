"""Celery application for Launchpad background task processing.

Replaces asyncio background loops with persistent, retryable, observable tasks.
Broker: Redis in ecosystem-redis namespace (DB 2).
"""

import os

from celery import Celery

REDIS_URL = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://:ecosystem-redis-2026@redis.ecosystem-redis.svc:6379/2",
)

app = Celery("launchpad", broker=REDIS_URL, backend=REDIS_URL)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=100,
)

app.conf.beat_schedule = {
    "ttl-enforcement": {
        "task": "tasks.lifecycle.enforce_ttl",
        "schedule": 300.0,
    },
    "session-cleanup": {
        "task": "tasks.lifecycle.reclaim_session",
        "schedule": 3600.0,
    },
    "capacity-sync": {
        "task": "tasks.capacity_sync.sync_cluster_capacity",
        "schedule": 60.0,
    },
    "feedback-sync": {
        "task": "tasks.feedback_sync.refresh_feedback_aggregates",
        "schedule": 300.0,
    },
    "proactive-health": {
        "task": "tasks.orchestration.run_proactive_health",
        "schedule": 120.0,
    },
    "rebalance-check": {
        "task": "tasks.orchestration.run_rebalance_check",
        "schedule": 600.0,
    },
    "fleet-enrichment": {
        "task": "tasks.fleet_enrichment.refresh_fleet_enrichment",
        "schedule": 300.0,
    },
}

app.autodiscover_tasks(["tasks"])

# Explicit imports to ensure tasks register with shared_task
import tasks.lifecycle  # noqa: F401, E402
import tasks.capacity_sync  # noqa: F401, E402
import tasks.feedback_sync  # noqa: F401, E402
import tasks.orchestration  # noqa: F401, E402
import tasks.fleet_enrichment  # noqa: F401, E402
