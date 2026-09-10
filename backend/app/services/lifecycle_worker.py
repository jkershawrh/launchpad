from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from app.domain.enums import SessionStatus, WorkshopStatus
from app.domain.lifecycle_jobs import (
    LifecycleJob,
    LifecycleJobOperation,
    LifecycleJobStatus,
)
from app.domain.models import LabSession, Workshop
from app.storage.lifecycle_jobs import LifecycleJobStore

logger = logging.getLogger("launchpad.lifecycle-worker")


def build_lifecycle_admin_view(
    jobs: list[LifecycleJob],
    *,
    enabled: bool,
    serialize_workshop_provisioning: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)

    def utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    counts = {status.value: 0 for status in LifecycleJobStatus}
    rows = []
    pending_ages = []
    reclaim_pending = 0
    takeovers = 0
    expired_leases = 0
    for job in sorted(jobs, key=lambda item: (item.priority, item.created_at, item.job_id)):
        status = job.status.value
        counts[status] += 1
        age_seconds = max(0, int((utc(now) - utc(job.updated_at)).total_seconds()))
        if job.status in {
            LifecycleJobStatus.QUEUED,
            LifecycleJobStatus.RUNNING,
            LifecycleJobStatus.CANCEL_REQUESTED,
        }:
            pending_ages.append(age_seconds)
        if (
            job.operation
            in {
                LifecycleJobOperation.RECLAIM_WORKSHOP,
                LifecycleJobOperation.RECLAIM_SESSION,
            }
            and job.status
            in {
                LifecycleJobStatus.QUEUED,
                LifecycleJobStatus.RUNNING,
                LifecycleJobStatus.CANCEL_REQUESTED,
            }
        ):
            reclaim_pending += 1
        takeovers += max(0, job.attempts - 1)
        if (
            job.lease_until
            and job.status
            in {LifecycleJobStatus.RUNNING, LifecycleJobStatus.CANCEL_REQUESTED}
            and utc(job.lease_until) <= utc(now)
        ):
            expired_leases += 1
        rows.append(
            {
                "job_id": job.job_id,
                "operation": job.operation.value,
                "aggregate_type": job.aggregate_type,
                "aggregate_id": job.aggregate_id,
                "cluster_ref": job.cluster_ref,
                "status": status,
                "priority": job.priority,
                "step": job.step,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "fencing_token": job.fencing_token,
                "lease_until": job.lease_until,
                "age_seconds": age_seconds,
                "last_error": job.last_error,
            }
        )
    return {
        "enabled": enabled,
        "workshop_provisioning_policy": (
            "serialized" if serialize_workshop_provisioning else "parallel"
        ),
        "summary": {
            **counts,
            "reclaim_pending": reclaim_pending,
            "takeovers": takeovers,
            "expired_leases": expired_leases,
            "oldest_pending_age_seconds": max(pending_ages, default=0),
        },
        "jobs": rows,
    }


class LifecycleQueueService:
    """Creates stable, cluster-bound jobs for API and reconciler callers."""

    PROVISION_PRIORITY = 50
    RECLAIM_PRIORITY = 10
    TTL_PRIORITY = 20
    RECONCILE_PRIORITY = 90

    def __init__(self, store: LifecycleJobStore) -> None:
        self.store = store

    def enqueue_workshop_provision(self, workshop: Workshop) -> LifecycleJob:
        if not workshop.cluster_ref:
            raise ValueError("Workshop cluster_ref must be persisted before enqueue")
        generation = int(workshop.metadata.get("lifecycle_provision_generation", 1))
        if generation < 1:
            raise ValueError("Workshop lifecycle provision generation must be positive")
        return self.store.enqueue(
            LifecycleJob(
                operation=LifecycleJobOperation.PROVISION_WORKSHOP,
                aggregate_type="workshop",
                aggregate_id=workshop.workshop_id,
                cluster_ref=workshop.cluster_ref,
                priority=self.PROVISION_PRIORITY,
                idempotency_key=(
                    f"workshop:{workshop.workshop_id}:provision:v{generation}"
                ),
                payload={"workshop_id": workshop.workshop_id},
            )
        )

    def enqueue_workshop_reclaim(self, workshop: Workshop) -> LifecycleJob:
        if not workshop.cluster_ref:
            raise ValueError("Workshop cluster_ref must be persisted before enqueue")
        self.store.request_cancel_for_aggregate(
            aggregate_type="workshop",
            aggregate_id=workshop.workshop_id,
            operations={LifecycleJobOperation.PROVISION_WORKSHOP},
        )
        return self.store.enqueue(
            LifecycleJob(
                operation=LifecycleJobOperation.RECLAIM_WORKSHOP,
                aggregate_type="workshop",
                aggregate_id=workshop.workshop_id,
                cluster_ref=workshop.cluster_ref,
                priority=self.RECLAIM_PRIORITY,
                idempotency_key=f"workshop:{workshop.workshop_id}:reclaim:v1",
                payload={"workshop_id": workshop.workshop_id},
            )
        )

    def enqueue_session_provision(self, session: LabSession) -> LifecycleJob:
        if not session.cluster_ref:
            raise ValueError("Session cluster_ref must be persisted before enqueue")
        return self.store.enqueue(
            LifecycleJob(
                operation=LifecycleJobOperation.PROVISION_SESSION,
                aggregate_type="session",
                aggregate_id=session.session_id,
                cluster_ref=session.cluster_ref,
                priority=self.PROVISION_PRIORITY,
                idempotency_key=f"session:{session.session_id}:provision:v1",
                payload={
                    "session_id": session.session_id,
                    "request_id": session.request_id,
                },
            )
        )

    def enqueue_session_reclaim(self, session: LabSession) -> LifecycleJob:
        if not session.cluster_ref:
            raise ValueError("Session cluster_ref must be persisted before enqueue")
        self.store.request_cancel_for_aggregate(
            aggregate_type="session",
            aggregate_id=session.session_id,
            operations={LifecycleJobOperation.PROVISION_SESSION},
        )
        return self.store.enqueue(
            LifecycleJob(
                operation=LifecycleJobOperation.RECLAIM_SESSION,
                aggregate_type="session",
                aggregate_id=session.session_id,
                cluster_ref=session.cluster_ref,
                priority=self.RECLAIM_PRIORITY,
                idempotency_key=f"session:{session.session_id}:reclaim:v1",
                payload={"session_id": session.session_id},
            )
        )

    def enqueue_ttl_cycle(self, cycle_id: str) -> LifecycleJob:
        return self.store.enqueue(
            LifecycleJob(
                operation=LifecycleJobOperation.ENFORCE_TTL,
                aggregate_type="system",
                aggregate_id="ttl-enforcement",
                priority=self.TTL_PRIORITY,
                idempotency_key=f"system:ttl:{cycle_id}",
                payload={"cycle_id": cycle_id},
                max_attempts=5,
            )
        )

    def enqueue_reconciliation_cycle(self, cycle_id: str) -> LifecycleJob:
        return self.store.enqueue(
            LifecycleJob(
                operation=LifecycleJobOperation.RECONCILE,
                aggregate_type="system",
                aggregate_id="resource-reconciliation",
                priority=self.RECONCILE_PRIORITY,
                idempotency_key=f"system:reconcile:{cycle_id}",
                payload={"cycle_id": cycle_id},
                max_attempts=5,
            )
        )

    def enqueue_interrupted_workshops(
        self, workshops: list[Workshop]
    ) -> list[LifecycleJob]:
        jobs = []
        for workshop in workshops:
            if not workshop.cluster_ref:
                logger.error(
                    "Interrupted workshop %s has no persisted cluster_ref; "
                    "refusing lifecycle recovery",
                    workshop.workshop_id,
                )
                continue
            if workshop.status in {
                WorkshopStatus.QUEUED,
                WorkshopStatus.PROVISIONING,
            }:
                jobs.append(self.enqueue_workshop_provision(workshop))
            elif workshop.status == WorkshopStatus.RECLAIMING:
                jobs.append(self.enqueue_workshop_reclaim(workshop))
        return jobs

    def enqueue_interrupted_sessions(
        self, sessions: list[LabSession]
    ) -> list[LifecycleJob]:
        jobs = []
        for session in sessions:
            interrupted = session.status in {
                SessionStatus.REQUESTED,
                SessionStatus.PROVISIONING,
                SessionStatus.VALIDATING,
                SessionStatus.VALIDATION_FAILED,
                SessionStatus.RESETTING,
                SessionStatus.CLEANUP_FAILED,
            }
            if not session.cluster_ref:
                if interrupted:
                    logger.error(
                        "Interrupted session %s has no persisted cluster_ref; "
                        "refusing lifecycle recovery",
                        session.session_id,
                    )
                continue
            if session.status in {
                SessionStatus.REQUESTED,
                SessionStatus.PROVISIONING,
                SessionStatus.VALIDATING,
                SessionStatus.VALIDATION_FAILED,
            }:
                jobs.append(self.enqueue_session_provision(session))
            elif session.status in {
                SessionStatus.RESETTING,
                SessionStatus.CLEANUP_FAILED,
            }:
                jobs.append(self.enqueue_session_reclaim(session))
        return jobs


class LifecycleWorker:
    """Claims durable jobs and delegates idempotent work to ProvisioningService."""

    def __init__(
        self,
        *,
        store: LifecycleJobStore,
        provisioning_service: Any,
        worker_id: str,
        lease_seconds: int = 120,
        heartbeat_interval_seconds: int = 15,
        serialize_workshop_provisioning: bool = False,
    ) -> None:
        if heartbeat_interval_seconds >= lease_seconds:
            logger.warning(
                "Lifecycle heartbeat interval (%ss) is not below lease (%ss)",
                heartbeat_interval_seconds,
                lease_seconds,
            )
        self.store = store
        self.provisioning_service = provisioning_service
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.serialize_workshop_provisioning = serialize_workshop_provisioning

    def _refresh_workshop(self, workshop_id: str) -> None:
        db = getattr(self.provisioning_service, "db", None)
        workshop_store = getattr(db, "workshops", None) if db else None
        if not workshop_store:
            return
        persisted = workshop_store.get(workshop_id)
        if persisted:
            self.provisioning_service._workshops[workshop_id] = persisted

    def _refresh_session(self, session_id: str) -> None:
        db = getattr(self.provisioning_service, "db", None)
        session_store = getattr(db, "sessions", None) if db else None
        if not session_store:
            return
        persisted = session_store.get(session_id)
        if not persisted:
            return
        self.provisioning_service._sessions[session_id] = persisted
        request_store = getattr(db, "requests", None)
        if request_store:
            request = request_store.get(persisted.request_id)
            if request:
                self.provisioning_service._requests[request.request_id] = request

    def _heartbeat_loop(
        self,
        job: LifecycleJob,
        stop: threading.Event,
        ownership_lost: threading.Event,
    ) -> None:
        while not stop.wait(self.heartbeat_interval_seconds):
            try:
                renewed = self.store.heartbeat(
                    job.job_id,
                    self.worker_id,
                    job.fencing_token,
                    lease_seconds=self.lease_seconds,
                )
            except Exception:
                logger.exception("Lifecycle heartbeat failed for %s", job.job_id)
                renewed = False
            if not renewed:
                ownership_lost.set()
                return

    def _execute(self, job: LifecycleJob):
        refresh = getattr(self.provisioning_service, "refresh_persisted_state", None)
        if refresh:
            refresh()
        lifecycle_guard = lambda: self.store.can_continue(
            job.job_id,
            self.worker_id,
            job.fencing_token,
        )
        if job.operation == LifecycleJobOperation.PROVISION_WORKSHOP:
            self._refresh_workshop(job.aggregate_id)
            return self.provisioning_service.run_queued_workshop(
                job.aggregate_id,
                lifecycle_guard=lifecycle_guard,
            )
        if job.operation == LifecycleJobOperation.RECLAIM_WORKSHOP:
            self._refresh_workshop(job.aggregate_id)
            return self.provisioning_service.reclaim_workshop(
                job.aggregate_id,
                lifecycle_guard=lifecycle_guard,
            )
        if job.operation == LifecycleJobOperation.PROVISION_SESSION:
            self._refresh_session(job.aggregate_id)
            return self.provisioning_service.run_queued_session(
                job.aggregate_id,
                lifecycle_guard=lifecycle_guard,
            )
        if job.operation == LifecycleJobOperation.RECLAIM_SESSION:
            self._refresh_session(job.aggregate_id)
            return self.provisioning_service.reclaim_session(
                job.aggregate_id,
                lifecycle_guard=lifecycle_guard,
            )
        if job.operation == LifecycleJobOperation.ENFORCE_TTL:
            return {
                "reclaimed_count": self.provisioning_service.enforce_ttl(
                    lifecycle_guard=lifecycle_guard
                )
            }
        if job.operation == LifecycleJobOperation.RECONCILE:
            from app.services.resource_reconciliation import reconcile_resources

            return reconcile_resources(
                self.provisioning_service,
                lifecycle_guard=lifecycle_guard,
            )
        raise ValueError(f"Unsupported lifecycle operation: {job.operation.value}")

    @staticmethod
    def _result_evidence(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return {
                key if not isinstance(value, list) else f"{key}_count": (
                    len(value) if isinstance(value, list) else value
                )
                for key, value in result.items()
                if isinstance(value, (bool, int, float, list))
            }
        evidence = {}
        status = getattr(result, "status", None)
        status_value = getattr(status, "value", status)
        if isinstance(result, LabSession):
            evidence["session_status"] = status_value
        else:
            evidence["workshop_status"] = status_value
        session_ids = getattr(result, "session_ids", None)
        if session_ids is not None:
            evidence["session_count"] = len(session_ids)
        return evidence

    def run_once(self) -> str:
        job = self.store.claim_next(
            self.worker_id,
            lease_seconds=self.lease_seconds,
            serialize_workshop_provisioning=self.serialize_workshop_provisioning,
        )
        if not job:
            return "idle"
        if not self.store.checkpoint(
            job.job_id,
            self.worker_id,
            job.fencing_token,
            step="execution-started",
        ):
            return "lost_ownership"

        stop = threading.Event()
        ownership_lost = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(job, stop, ownership_lost),
            daemon=True,
            name=f"lifecycle-heartbeat-{job.job_id}",
        )
        heartbeat.start()
        try:
            if self.store.is_cancel_requested(
                job.job_id, self.worker_id, job.fencing_token
            ):
                acknowledged = self.store.acknowledge_cancel(
                    job.job_id, self.worker_id, job.fencing_token
                )
                return "cancelled" if acknowledged else "lost_ownership"
            result = self._execute(job)
            if ownership_lost.is_set():
                return "lost_ownership"
            if not self.store.checkpoint(
                job.job_id,
                self.worker_id,
                job.fencing_token,
                step="execution-finished",
                evidence=self._result_evidence(result),
            ):
                return "lost_ownership"
            return (
                "succeeded"
                if self.store.complete(
                    job.job_id, self.worker_id, job.fencing_token
                )
                else "lost_ownership"
            )
        except Exception as exc:
            logger.exception("Lifecycle job %s failed", job.job_id)
            if ownership_lost.is_set():
                return "lost_ownership"
            retry_delay = min(300, 2 ** max(1, job.attempts))
            changed = self.store.fail(
                job.job_id,
                self.worker_id,
                job.fencing_token,
                error=str(exc),
                retry_delay_seconds=retry_delay,
            )
            return "retrying" if changed else "lost_ownership"
        finally:
            stop.set()
            heartbeat.join(timeout=1)
