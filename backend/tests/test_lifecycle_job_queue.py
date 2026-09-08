"""TDD contracts for distributed lifecycle ownership.

These tests intentionally exercise the queue independently from Kubernetes so
provisioning and reclaim ownership can be proven deterministically.
"""

from datetime import UTC, datetime, timedelta

from app.domain.lifecycle_jobs import (
    LifecycleJob,
    LifecycleJobOperation,
    LifecycleJobStatus,
)
from app.storage.lifecycle_jobs import InMemoryLifecycleJobStore

BASE_TIME = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = BASE_TIME

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def job(
    operation: LifecycleJobOperation,
    *,
    aggregate_id: str = "workshop-1",
    priority: int = 50,
    idempotency_key: str | None = None,
) -> LifecycleJob:
    return LifecycleJob(
        operation=operation,
        aggregate_type="workshop",
        aggregate_id=aggregate_id,
        cluster_ref="arena",
        priority=priority,
        idempotency_key=idempotency_key or f"{operation.value}:{aggregate_id}",
        next_attempt_at=BASE_TIME,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def test_enqueue_is_idempotent() -> None:
    store = InMemoryLifecycleJobStore()

    first = store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    duplicate = store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))

    assert duplicate.job_id == first.job_id
    assert len(store.list_all()) == 1


def test_reclaim_priority_is_claimed_before_provisioning() -> None:
    store = InMemoryLifecycleJobStore()
    store.enqueue(
        job(
            LifecycleJobOperation.PROVISION_WORKSHOP,
            aggregate_id="workshop-provision",
            priority=50,
        )
    )
    reclaim = store.enqueue(
        job(
            LifecycleJobOperation.RECLAIM_WORKSHOP,
            aggregate_id="workshop-reclaim",
            priority=10,
        )
    )

    claimed = store.claim_next("worker-a", lease_seconds=30)

    assert claimed is not None
    assert claimed.job_id == reclaim.job_id


def test_only_one_worker_can_own_an_aggregate() -> None:
    store = InMemoryLifecycleJobStore()
    first = store.enqueue(
        job(
            LifecycleJobOperation.PROVISION_WORKSHOP,
            idempotency_key="provision:workshop-1",
        )
    )
    store.enqueue(
        job(
            LifecycleJobOperation.RECLAIM_WORKSHOP,
            priority=10,
            idempotency_key="reclaim:workshop-1",
        )
    )

    claimed = store.claim_next("worker-a", lease_seconds=30)
    blocked = store.claim_next("worker-b", lease_seconds=30)

    assert claimed is not None
    assert claimed.job_id in {item.job_id for item in store.list_all()}
    assert blocked is None
    assert first.aggregate_id == claimed.aggregate_id


def test_expired_lease_is_taken_over_with_a_new_fencing_token() -> None:
    clock = Clock()
    store = InMemoryLifecycleJobStore(clock=clock)
    queued = store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    first = store.claim_next("worker-a", lease_seconds=30)
    assert first is not None

    clock.advance(seconds=31)
    takeover = store.claim_next("worker-b", lease_seconds=30)

    assert takeover is not None
    assert takeover.job_id == queued.job_id
    assert takeover.owner_id == "worker-b"
    assert takeover.fencing_token == first.fencing_token + 1
    assert takeover.attempts == first.attempts + 1


def test_stale_worker_cannot_heartbeat_checkpoint_or_complete_after_takeover() -> None:
    clock = Clock()
    store = InMemoryLifecycleJobStore(clock=clock)
    store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    stale = store.claim_next("worker-a", lease_seconds=30)
    assert stale is not None

    clock.advance(seconds=31)
    owner = store.claim_next("worker-b", lease_seconds=30)
    assert owner is not None

    assert not store.heartbeat(stale.job_id, "worker-a", stale.fencing_token, lease_seconds=30)
    assert not store.checkpoint(
        stale.job_id,
        "worker-a",
        stale.fencing_token,
        step="namespace-created",
    )
    assert not store.complete(stale.job_id, "worker-a", stale.fencing_token)
    assert store.heartbeat(owner.job_id, "worker-b", owner.fencing_token, lease_seconds=30)


def test_expired_owner_cannot_resurrect_a_lease_before_takeover() -> None:
    clock = Clock()
    store = InMemoryLifecycleJobStore(clock=clock)
    store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    owner = store.claim_next("worker-a", lease_seconds=30)
    assert owner is not None

    clock.advance(seconds=31)

    assert not store.heartbeat(
        owner.job_id, "worker-a", owner.fencing_token, lease_seconds=30
    )
    assert not store.can_continue(owner.job_id, "worker-a", owner.fencing_token)


def test_only_current_running_owner_can_continue_cluster_mutations() -> None:
    store = InMemoryLifecycleJobStore()
    store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    owner = store.claim_next("worker-a", lease_seconds=30)
    assert owner is not None

    assert store.can_continue(owner.job_id, "worker-a", owner.fencing_token)
    assert not store.can_continue(owner.job_id, "worker-b", owner.fencing_token)
    assert store.request_cancel(owner.job_id)
    assert not store.can_continue(owner.job_id, "worker-a", owner.fencing_token)


def test_checkpoint_is_durable_and_merges_evidence() -> None:
    store = InMemoryLifecycleJobStore()
    store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    claimed = store.claim_next("worker-a", lease_seconds=30)
    assert claimed is not None

    assert store.checkpoint(
        claimed.job_id,
        "worker-a",
        claimed.fencing_token,
        step="seat-1-ready",
        evidence={"session_id": "session-1"},
    )
    persisted = store.get(claimed.job_id)

    assert persisted is not None
    assert persisted.step == "seat-1-ready"
    assert persisted.evidence == {"session_id": "session-1"}


def test_cancel_requested_job_releases_aggregate_for_reclaim() -> None:
    store = InMemoryLifecycleJobStore()
    provision = store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    running = store.claim_next("worker-a", lease_seconds=30)
    assert running is not None

    assert store.request_cancel(provision.job_id)
    reclaim = store.enqueue(
        job(
            LifecycleJobOperation.RECLAIM_WORKSHOP,
            priority=10,
            idempotency_key="reclaim:workshop-1",
        )
    )
    assert store.claim_next("worker-b", lease_seconds=30) is None
    assert store.acknowledge_cancel(running.job_id, "worker-a", running.fencing_token)

    claimed_reclaim = store.claim_next("worker-b", lease_seconds=30)
    assert claimed_reclaim is not None
    assert claimed_reclaim.job_id == reclaim.job_id


def test_cancel_request_stops_lease_renewal_for_a_blocked_worker() -> None:
    store = InMemoryLifecycleJobStore()
    queued = store.enqueue(job(LifecycleJobOperation.PROVISION_WORKSHOP))
    running = store.claim_next("worker-a", lease_seconds=30)
    assert running is not None

    assert store.request_cancel(queued.job_id)
    assert not store.heartbeat(
        running.job_id,
        "worker-a",
        running.fencing_token,
        lease_seconds=30,
    )


def test_cancel_for_aggregate_changes_only_matching_active_operations() -> None:
    store = InMemoryLifecycleJobStore()
    matching = store.enqueue(
        job(LifecycleJobOperation.PROVISION_WORKSHOP, priority=1)
    )
    unrelated = store.enqueue(
        job(
            LifecycleJobOperation.PROVISION_WORKSHOP,
            aggregate_id="workshop-2",
        )
    )
    terminal = store.enqueue(
        job(
            LifecycleJobOperation.RECONCILE,
            idempotency_key="reconcile:workshop-1",
        )
    )
    terminal_owner = store.claim_next("worker-a", lease_seconds=30)
    assert terminal_owner is not None
    assert terminal_owner.job_id == matching.job_id
    assert store.complete(
        terminal_owner.job_id,
        "worker-a",
        terminal_owner.fencing_token,
    )

    changed = store.request_cancel_for_aggregate(
        aggregate_type="workshop",
        aggregate_id="workshop-1",
        operations={LifecycleJobOperation.RECONCILE},
    )

    assert changed == 1
    assert store.get(terminal.job_id).status == LifecycleJobStatus.CANCELLED
    assert store.get(matching.job_id).status == LifecycleJobStatus.SUCCEEDED
    assert store.get(unrelated.job_id).status == LifecycleJobStatus.QUEUED


def test_failure_requeues_until_max_attempts_then_becomes_terminal() -> None:
    clock = Clock()
    store = InMemoryLifecycleJobStore(clock=clock)
    store.enqueue(
        job(LifecycleJobOperation.PROVISION_WORKSHOP).model_copy(update={"max_attempts": 2})
    )

    first = store.claim_next("worker-a", lease_seconds=30)
    assert first is not None
    assert store.fail(
        first.job_id,
        "worker-a",
        first.fencing_token,
        error="temporary failure",
        retry_delay_seconds=10,
    )
    assert store.get(first.job_id).status == LifecycleJobStatus.QUEUED

    clock.advance(seconds=10)
    second = store.claim_next("worker-b", lease_seconds=30)
    assert second is not None
    assert store.fail(
        second.job_id,
        "worker-b",
        second.fencing_token,
        error="permanent failure",
        retry_delay_seconds=10,
    )
    assert store.get(second.job_id).status == LifecycleJobStatus.FAILED


def test_migration_defines_job_and_aggregate_lease_tables() -> None:
    migration = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "migrations/005_lifecycle_jobs.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS lifecycle_jobs" in migration
    assert "CREATE TABLE IF NOT EXISTS lifecycle_aggregate_leases" in migration
    assert "idempotency_key" in migration
    assert "fencing_token" in migration
    assert "lease_until" in migration
    assert "next_attempt_at" in migration
