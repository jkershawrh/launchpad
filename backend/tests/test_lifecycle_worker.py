from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.domain.enums import (
    CatalogCategory,
    LabRequestStatus,
    SessionStatus,
    WorkshopStatus,
)
from app.domain.lifecycle_jobs import LifecycleJobOperation, LifecycleJobStatus
from app.domain.models import LabRequest, LabSession, Workshop
from app.services.lifecycle_worker import LifecycleQueueService, LifecycleWorker
from app.services.provisioning import ProvisioningService
from app.storage.lifecycle_jobs import InMemoryLifecycleJobStore


def workshop(*, status: WorkshopStatus = WorkshopStatus.QUEUED) -> Workshop:
    return Workshop(
        workshop_id="workshop-1",
        tenant_id="tenant-1",
        catalog_item_id="catalog-1",
        num_users=1,
        cluster_ref="arena",
        status=status,
    )


def lab_request() -> LabRequest:
    return LabRequest(
        request_id="request-1",
        tenant_id="tenant-1",
        requester_id="participant-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
        status=LabRequestStatus.ACCEPTED,
        metadata={"target_cluster": "arena"},
    )


def lab_session(*, status: SessionStatus = SessionStatus.REQUESTED) -> LabSession:
    return LabSession(
        session_id="session-1",
        request_id="request-1",
        tenant_id="tenant-1",
        catalog_item_id="catalog-1",
        cluster_ref="arena",
        status=status,
    )


def test_prepare_session_persists_placement_before_job_enqueue() -> None:
    service = ProvisioningService()
    accepted = service.submit_request(lab_request())

    prepared = service.prepare_session_provision(accepted.request_id)

    assert prepared.status == SessionStatus.REQUESTED
    assert prepared.cluster_ref == "arena"
    assert service.get_request(accepted.request_id).metadata["target_cluster"] == (
        "arena"
    )


def test_queued_session_reuses_prepared_identity_and_reaches_ready() -> None:
    service = ProvisioningService()
    accepted = service.submit_request(lab_request())
    prepared = service.prepare_session_provision(accepted.request_id)

    ready = service.run_queued_session(prepared.session_id)

    assert ready.session_id == prepared.session_id
    assert ready.cluster_ref == "arena"
    assert ready.status == SessionStatus.READY


def test_interrupted_session_waits_for_namespace_deletion_before_reprovision(
    monkeypatch,
) -> None:
    cleanup = Mock()
    service = ProvisioningService(cleanup=cleanup)
    accepted = service.submit_request(lab_request())
    prepared = service.prepare_session_provision(accepted.request_id)
    interrupted = prepared.model_copy(
        update={
            "status": SessionStatus.PROVISIONING,
            "namespace": "launchpad-interrupted-session",
        }
    )
    service._sessions[prepared.session_id] = interrupted
    service._save_session(interrupted)
    monkeypatch.setenv("INTERRUPTED_NAMESPACE_DELETE_TIMEOUT", "37")

    ready = service.run_queued_session(prepared.session_id)

    cleanup.cleanup.assert_called_once_with(
        "launchpad-interrupted-session", timeout=37
    )
    assert ready.session_id == prepared.session_id
    assert ready.status == SessionStatus.READY


def test_queue_service_enqueues_idempotent_cluster_bound_provision() -> None:
    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)

    first = queue.enqueue_workshop_provision(workshop())
    duplicate = queue.enqueue_workshop_provision(workshop())

    assert first.job_id == duplicate.job_id
    assert first.operation == LifecycleJobOperation.PROVISION_WORKSHOP
    assert first.cluster_ref == "arena"
    assert first.idempotency_key == "workshop:workshop-1:provision:v1"


def test_reclaim_request_cancels_provision_before_it_can_claim_aggregate() -> None:
    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)
    provision = queue.enqueue_workshop_provision(workshop())
    running = store.claim_next("worker-a", lease_seconds=30)
    assert running is not None

    reclaim = queue.enqueue_workshop_reclaim(
        workshop(status=WorkshopStatus.RECLAIMING)
    )

    assert store.get(provision.job_id).status == LifecycleJobStatus.CANCEL_REQUESTED
    assert reclaim.priority < provision.priority
    assert store.claim_next("worker-b", lease_seconds=30) is None


def test_session_jobs_are_cluster_bound_and_reclaim_cancels_provision() -> None:
    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)
    provision = queue.enqueue_session_provision(lab_session())
    running = store.claim_next("worker-a", lease_seconds=30)
    assert running is not None

    reclaim = queue.enqueue_session_reclaim(
        lab_session(status=SessionStatus.RESETTING)
    )

    assert provision.aggregate_type == "session"
    assert provision.cluster_ref == "arena"
    assert store.get(provision.job_id).status == LifecycleJobStatus.CANCEL_REQUESTED
    assert reclaim.priority < provision.priority


def test_worker_executes_and_validates_prepared_session() -> None:
    store = InMemoryLifecycleJobStore()
    LifecycleQueueService(store).enqueue_session_provision(lab_session())
    ready = lab_session(status=SessionStatus.READY)
    provisioning = SimpleNamespace(
        db=None,
        _sessions={ready.session_id: ready},
        _workshops={},
        run_queued_session=Mock(return_value=ready),
    )

    result = LifecycleWorker(
        store=store,
        provisioning_service=provisioning,
        worker_id="worker-a",
        lease_seconds=30,
        heartbeat_interval_seconds=60,
    ).run_once()

    assert result == "succeeded"
    provisioning.run_queued_session.assert_called_once()
    assert provisioning.run_queued_session.call_args.args == ("session-1",)
    assert callable(
        provisioning.run_queued_session.call_args.kwargs["lifecycle_guard"]
    )
    assert store.list_all()[0].evidence["session_status"] == "ready"


def test_worker_executes_provision_and_records_completion_evidence() -> None:
    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)
    queue.enqueue_workshop_provision(workshop())
    ready = workshop(status=WorkshopStatus.READY)
    provisioning = SimpleNamespace(
        db=None,
        _workshops={ready.workshop_id: ready},
        run_queued_workshop=Mock(return_value=ready),
        reclaim_workshop=Mock(),
    )
    worker = LifecycleWorker(
        store=store,
        provisioning_service=provisioning,
        worker_id="worker-a",
        lease_seconds=30,
        heartbeat_interval_seconds=60,
    )

    result = worker.run_once()

    assert result == "succeeded"
    persisted = store.list_all()[0]
    assert persisted.status == LifecycleJobStatus.SUCCEEDED
    assert persisted.evidence["workshop_status"] == "ready"
    provisioning.run_queued_workshop.assert_called_once()
    assert provisioning.run_queued_workshop.call_args.args == ("workshop-1",)
    lifecycle_guard = provisioning.run_queued_workshop.call_args.kwargs[
        "lifecycle_guard"
    ]
    assert callable(lifecycle_guard)


def test_worker_refreshes_workshop_from_durable_store_before_execution() -> None:
    store = InMemoryLifecycleJobStore()
    LifecycleQueueService(store).enqueue_workshop_provision(workshop())
    durable = workshop(status=WorkshopStatus.QUEUED)
    workshop_store = SimpleNamespace(get=Mock(return_value=durable))
    provisioning = SimpleNamespace(
        db=SimpleNamespace(workshops=workshop_store),
        _workshops={},
        run_queued_workshop=Mock(
            side_effect=lambda workshop_id, **_kwargs: provisioning._workshops[
                workshop_id
            ].model_copy(update={"status": WorkshopStatus.READY})
        ),
        reclaim_workshop=Mock(),
    )

    result = LifecycleWorker(
        store=store,
        provisioning_service=provisioning,
        worker_id="worker-a",
        lease_seconds=30,
        heartbeat_interval_seconds=60,
    ).run_once()

    assert result == "succeeded"
    workshop_store.get.assert_called_once_with("workshop-1")
    assert provisioning._workshops["workshop-1"] == durable


def test_worker_failure_is_requeued_with_error() -> None:
    store = InMemoryLifecycleJobStore()
    LifecycleQueueService(store).enqueue_workshop_provision(workshop())
    provisioning = SimpleNamespace(
        db=None,
        _workshops={},
        run_queued_workshop=Mock(side_effect=RuntimeError("cluster unavailable")),
        reclaim_workshop=Mock(),
    )
    worker = LifecycleWorker(
        store=store,
        provisioning_service=provisioning,
        worker_id="worker-a",
        lease_seconds=30,
        heartbeat_interval_seconds=60,
    )

    result = worker.run_once()

    assert result == "retrying"
    persisted = store.list_all()[0]
    assert persisted.status == LifecycleJobStatus.QUEUED
    assert persisted.last_error == "cluster unavailable"


def test_successful_retry_clears_stale_lifecycle_error() -> None:
    now = [datetime.now(UTC)]
    store = InMemoryLifecycleJobStore(clock=lambda: now[0])
    LifecycleQueueService(store).enqueue_workshop_provision(workshop())
    now[0] += timedelta(seconds=1)
    ready = workshop(status=WorkshopStatus.READY)
    provisioning = SimpleNamespace(
        db=None,
        _workshops={},
        run_queued_workshop=Mock(
            side_effect=[RuntimeError("transient failure"), ready]
        ),
        reclaim_workshop=Mock(),
    )
    worker = LifecycleWorker(
        store=store,
        provisioning_service=provisioning,
        worker_id="worker-a",
        lease_seconds=30,
        heartbeat_interval_seconds=60,
    )

    assert worker.run_once() == "retrying"
    assert store.list_all()[0].last_error == "transient failure"
    now[0] += timedelta(seconds=3)
    assert worker.run_once() == "succeeded"

    persisted = store.list_all()[0]
    assert persisted.status == LifecycleJobStatus.SUCCEEDED
    assert persisted.last_error is None


def test_worker_does_not_report_success_after_losing_fence() -> None:
    store = InMemoryLifecycleJobStore()
    LifecycleQueueService(store).enqueue_workshop_provision(workshop())
    ready = workshop(status=WorkshopStatus.READY)
    provisioning = SimpleNamespace(
        db=None,
        _workshops={},
        run_queued_workshop=Mock(return_value=ready),
        reclaim_workshop=Mock(),
    )
    original_complete = store.complete
    store.complete = Mock(return_value=False)
    worker = LifecycleWorker(
        store=store,
        provisioning_service=provisioning,
        worker_id="worker-a",
        lease_seconds=30,
        heartbeat_interval_seconds=60,
    )

    assert worker.run_once() == "lost_ownership"
    store.complete = original_complete


def test_system_cycle_jobs_are_idempotent_and_have_separate_aggregates() -> None:
    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)

    ttl = queue.enqueue_ttl_cycle("20260908T1200")
    ttl_duplicate = queue.enqueue_ttl_cycle("20260908T1200")
    reconcile = queue.enqueue_reconciliation_cycle("20260908T1200")

    assert ttl.job_id == ttl_duplicate.job_id
    assert ttl.operation == LifecycleJobOperation.ENFORCE_TTL
    assert reconcile.operation == LifecycleJobOperation.RECONCILE
    assert ttl.aggregate_id != reconcile.aggregate_id
    assert len(store.list_all()) == 2


def test_worker_executes_ttl_as_a_durable_system_job() -> None:
    store = InMemoryLifecycleJobStore()
    LifecycleQueueService(store).enqueue_ttl_cycle("20260908T1200")
    provisioning = SimpleNamespace(
        db=None,
        _workshops={},
        enforce_ttl=Mock(return_value=3),
    )

    result = LifecycleWorker(
        store=store,
        provisioning_service=provisioning,
        worker_id="worker-a",
        lease_seconds=30,
        heartbeat_interval_seconds=60,
    ).run_once()

    assert result == "succeeded"
    provisioning.enforce_ttl.assert_called_once()
    assert callable(provisioning.enforce_ttl.call_args.kwargs["lifecycle_guard"])
    persisted = store.list_all()[0]
    assert persisted.evidence["reclaimed_count"] == 3


def test_bootstrap_enqueues_only_interrupted_cluster_bound_workshops() -> None:
    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)
    provisioning = workshop(status=WorkshopStatus.PROVISIONING)
    reclaiming = workshop(status=WorkshopStatus.RECLAIMING).model_copy(
        update={"workshop_id": "workshop-2"}
    )
    ready = workshop(status=WorkshopStatus.READY).model_copy(
        update={"workshop_id": "workshop-3"}
    )
    unplaced = workshop(status=WorkshopStatus.QUEUED).model_copy(
        update={"workshop_id": "workshop-4", "cluster_ref": None}
    )

    jobs = queue.enqueue_interrupted_workshops(
        [provisioning, reclaiming, ready, unplaced]
    )

    assert {job.operation for job in jobs} == {
        LifecycleJobOperation.PROVISION_WORKSHOP,
        LifecycleJobOperation.RECLAIM_WORKSHOP,
    }
    assert {job.aggregate_id for job in jobs} == {"workshop-1", "workshop-2"}


def test_bootstrap_enqueues_interrupted_sessions_for_resume_or_reclaim() -> None:
    store = InMemoryLifecycleJobStore()
    queue = LifecycleQueueService(store)
    provisioning = lab_session(status=SessionStatus.PROVISIONING)
    reclaiming = lab_session(status=SessionStatus.RESETTING).model_copy(
        update={"session_id": "session-2"}
    )
    ready = lab_session(status=SessionStatus.READY).model_copy(
        update={"session_id": "session-3"}
    )
    unplaced = lab_session(status=SessionStatus.REQUESTED).model_copy(
        update={"session_id": "session-4", "cluster_ref": None}
    )

    jobs = queue.enqueue_interrupted_sessions(
        [provisioning, reclaiming, ready, unplaced]
    )

    assert {job.operation for job in jobs} == {
        LifecycleJobOperation.PROVISION_SESSION,
        LifecycleJobOperation.RECLAIM_SESSION,
    }
    assert {job.aggregate_id for job in jobs} == {"session-1", "session-2"}


def test_ha_worker_startup_does_not_mutate_resources_outside_a_job(
    monkeypatch,
) -> None:
    empty_store = SimpleNamespace(list_all=Mock(return_value=[]))
    db = SimpleNamespace(
        sessions=empty_store,
        requests=empty_store,
        workshops=empty_store,
    )
    monkeypatch.setenv("LIFECYCLE_HA_ENABLED", "true")

    with patch.object(ProvisioningService, "_cleanup_orphaned_sessions") as cleanup:
        ProvisioningService(db_stores=db)

    cleanup.assert_not_called()


def test_api_reads_refresh_session_and_workshop_state_written_by_workers() -> None:
    stale_session = lab_session(status=SessionStatus.REQUESTED)
    ready_session = stale_session.model_copy(update={"status": SessionStatus.READY})
    stale_workshop = workshop(status=WorkshopStatus.QUEUED)
    ready_workshop = stale_workshop.model_copy(update={"status": WorkshopStatus.READY})
    empty_store = SimpleNamespace(list_all=Mock(return_value=[]))
    db = SimpleNamespace(
        sessions=SimpleNamespace(
            list_all=Mock(return_value=[stale_session]),
            get=Mock(return_value=ready_session),
        ),
        requests=empty_store,
        workshops=SimpleNamespace(
            list_all=Mock(return_value=[stale_workshop]),
            get=Mock(return_value=ready_workshop),
        ),
    )
    service = ProvisioningService(db_stores=db)

    assert service.get_session(stale_session.session_id).status == SessionStatus.READY
    assert service.get_workshop(stale_workshop.workshop_id).status == (
        WorkshopStatus.READY
    )
