"""PostgreSQL integration proof for cross-process lifecycle ownership."""

import os
import threading
import time

import pytest
from app.domain.lifecycle_jobs import (
    LifecycleJob,
    LifecycleJobOperation,
    LifecycleJobStatus,
)
from app.storage import database
from app.storage.lifecycle_jobs import PostgresLifecycleJobStore

TEST_DATABASE_URL = os.environ.get("LIFECYCLE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="LIFECYCLE_TEST_DATABASE_URL is not configured",
)


@pytest.fixture(autouse=True)
def lifecycle_schema(monkeypatch):
    import psycopg2

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL or "")
    database._initialize_database(psycopg2, TEST_DATABASE_URL)
    conn = psycopg2.connect(TEST_DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE lifecycle_jobs, lifecycle_aggregate_leases CASCADE")
    conn.commit()
    conn.close()
    yield


def lifecycle_job(*, idempotency_key: str = "workshop:one:provision:v1"):
    return LifecycleJob(
        operation=LifecycleJobOperation.PROVISION_WORKSHOP,
        aggregate_type="workshop",
        aggregate_id="workshop-one",
        cluster_ref="arena",
        idempotency_key=idempotency_key,
    )


def test_postgres_enqueue_is_idempotent_across_store_instances() -> None:
    first = PostgresLifecycleJobStore().enqueue(lifecycle_job())
    duplicate = PostgresLifecycleJobStore().enqueue(lifecycle_job())

    assert duplicate.job_id == first.job_id
    assert len(PostgresLifecycleJobStore().list_all()) == 1


def test_postgres_aggregate_lease_allows_only_one_concurrent_owner() -> None:
    store = PostgresLifecycleJobStore()
    store.enqueue(lifecycle_job())
    store.enqueue(
        LifecycleJob(
            operation=LifecycleJobOperation.RECLAIM_WORKSHOP,
            aggregate_type="workshop",
            aggregate_id="workshop-one",
            cluster_ref="arena",
            priority=10,
            idempotency_key="workshop:one:reclaim:v1",
        )
    )
    barrier = threading.Barrier(3)
    claims = []

    def claim(worker_id: str) -> None:
        barrier.wait()
        claims.append(PostgresLifecycleJobStore().claim_next(worker_id, lease_seconds=30))

    first = threading.Thread(target=claim, args=("worker-a",))
    second = threading.Thread(target=claim, args=("worker-b",))
    first.start()
    second.start()
    barrier.wait()
    first.join(timeout=5)
    second.join(timeout=5)

    assert sum(item is not None for item in claims) == 1


def test_postgres_takeover_fences_the_stale_worker() -> None:
    store = PostgresLifecycleJobStore()
    store.enqueue(lifecycle_job())
    stale = store.claim_next("worker-a", lease_seconds=1)
    assert stale is not None
    time.sleep(1.1)

    owner = PostgresLifecycleJobStore().claim_next("worker-b", lease_seconds=30)

    assert owner is not None
    assert owner.job_id == stale.job_id
    assert owner.fencing_token == stale.fencing_token + 1
    assert not store.complete(stale.job_id, "worker-a", stale.fencing_token)
    assert store.complete(owner.job_id, "worker-b", owner.fencing_token)


def test_postgres_cancel_for_aggregate_is_atomic_and_scoped() -> None:
    store = PostgresLifecycleJobStore()
    matching = store.enqueue(lifecycle_job())
    unrelated = store.enqueue(
        LifecycleJob(
            operation=LifecycleJobOperation.PROVISION_WORKSHOP,
            aggregate_type="workshop",
            aggregate_id="workshop-two",
            cluster_ref="arena",
            idempotency_key="workshop:two:provision:v1",
        )
    )

    changed = store.request_cancel_for_aggregate(
        aggregate_type="workshop",
        aggregate_id="workshop-one",
        operations={LifecycleJobOperation.PROVISION_WORKSHOP},
    )

    assert changed == 1
    assert store.get(matching.job_id).status == LifecycleJobStatus.CANCELLED
    assert store.get(unrelated.job_id).status == LifecycleJobStatus.QUEUED


def test_postgres_expired_cancel_is_closed_before_reclaim_takeover() -> None:
    store = PostgresLifecycleJobStore()
    provision = store.enqueue(lifecycle_job())
    owner = store.claim_next("worker-a", lease_seconds=1)
    assert owner is not None
    assert store.can_continue(owner.job_id, "worker-a", owner.fencing_token)
    assert store.request_cancel(provision.job_id)
    store.enqueue(
        LifecycleJob(
            operation=LifecycleJobOperation.RECLAIM_WORKSHOP,
            aggregate_type="workshop",
            aggregate_id="workshop-one",
            cluster_ref="arena",
            priority=10,
            idempotency_key="workshop:one:reclaim:v1",
        )
    )
    time.sleep(1.1)

    reclaim = store.claim_next("worker-b", lease_seconds=30)

    assert reclaim is not None
    assert reclaim.operation == LifecycleJobOperation.RECLAIM_WORKSHOP
    assert store.get(provision.job_id).status == LifecycleJobStatus.CANCELLED
    assert not store.can_continue(owner.job_id, "worker-a", owner.fencing_token)


def test_postgres_cancel_request_stops_lease_renewal() -> None:
    store = PostgresLifecycleJobStore()
    queued = store.enqueue(lifecycle_job())
    owner = store.claim_next("worker-a", lease_seconds=30)
    assert owner is not None

    assert store.request_cancel(queued.job_id)
    assert not store.heartbeat(
        owner.job_id,
        "worker-a",
        owner.fencing_token,
        lease_seconds=30,
    )
