from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.domain.lifecycle_jobs import (
    TERMINAL_LIFECYCLE_JOB_STATUSES,
    LifecycleJob,
    LifecycleJobOperation,
    LifecycleJobStatus,
)
from app.storage.stores import PersistenceUnavailableError, _get_sync_conn


class LifecycleJobStore(Protocol):
    def enqueue(self, job: LifecycleJob) -> LifecycleJob: ...

    def get(self, job_id: str) -> LifecycleJob | None: ...

    def list_all(self) -> list[LifecycleJob]: ...

    def claim_next(self, worker_id: str, *, lease_seconds: int) -> LifecycleJob | None: ...

    def heartbeat(
        self, job_id: str, worker_id: str, fencing_token: int, *, lease_seconds: int
    ) -> bool: ...

    def checkpoint(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        step: str,
        evidence: dict | None = None,
    ) -> bool: ...

    def complete(self, job_id: str, worker_id: str, fencing_token: int) -> bool: ...

    def fail(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        error: str,
        retry_delay_seconds: int,
    ) -> bool: ...

    def request_cancel(self, job_id: str) -> bool: ...

    def can_continue(self, job_id: str, worker_id: str, fencing_token: int) -> bool: ...

    def request_cancel_for_aggregate(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        operations: set[LifecycleJobOperation],
    ) -> int: ...

    def acknowledge_cancel(self, job_id: str, worker_id: str, fencing_token: int) -> bool: ...

    def is_cancel_requested(
        self, job_id: str, worker_id: str, fencing_token: int
    ) -> bool: ...


class InMemoryLifecycleJobStore:
    """Thread-safe deterministic implementation used by unit tests and local mode."""

    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._jobs: dict[str, LifecycleJob] = {}
        self._idempotency: dict[str, str] = {}
        self._leases: dict[tuple[str, str], dict] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _copy(job: LifecycleJob) -> LifecycleJob:
        return job.model_copy(deep=True)

    def enqueue(self, job: LifecycleJob) -> LifecycleJob:
        with self._lock:
            existing_id = self._idempotency.get(job.idempotency_key)
            if existing_id:
                return self._copy(self._jobs[existing_id])
            persisted = self._copy(job)
            self._jobs[persisted.job_id] = persisted
            self._idempotency[persisted.idempotency_key] = persisted.job_id
            self._leases.setdefault(
                (persisted.aggregate_type, persisted.aggregate_id),
                {
                    "active_job_id": None,
                    "owner_id": None,
                    "lease_until": None,
                    "fencing_token": 0,
                },
            )
            return self._copy(persisted)

    def get(self, job_id: str) -> LifecycleJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._copy(job) if job else None

    def list_all(self) -> list[LifecycleJob]:
        with self._lock:
            return [self._copy(job) for job in self._jobs.values()]

    def _lease_is_available(self, job: LifecycleJob, now: datetime) -> bool:
        lease = self._leases[(job.aggregate_type, job.aggregate_id)]
        return lease["lease_until"] is None or lease["lease_until"] <= now

    def _expire_abandoned_cancellations(self, now: datetime) -> None:
        for job_id, job in list(self._jobs.items()):
            if job.status != LifecycleJobStatus.CANCEL_REQUESTED:
                continue
            if not self._lease_is_available(job, now):
                continue
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": LifecycleJobStatus.CANCELLED,
                    "owner_id": None,
                    "lease_until": None,
                    "completed_at": now,
                    "updated_at": now,
                }
            )

    def claim_next(self, worker_id: str, *, lease_seconds: int) -> LifecycleJob | None:
        now = self._clock()
        with self._lock:
            self._expire_abandoned_cancellations(now)
            candidates = [
                job
                for job in self._jobs.values()
                if job.next_attempt_at <= now
                and (
                    job.status == LifecycleJobStatus.QUEUED
                    or (
                        job.status == LifecycleJobStatus.RUNNING
                        and job.lease_until is not None
                        and job.lease_until <= now
                    )
                )
                and self._lease_is_available(job, now)
            ]
            if not candidates:
                return None
            selected = min(
                candidates,
                key=lambda item: (
                    item.priority,
                    item.next_attempt_at,
                    item.created_at,
                    item.job_id,
                ),
            )
            lease_key = (selected.aggregate_type, selected.aggregate_id)
            lease = self._leases[lease_key]
            fencing_token = int(lease["fencing_token"]) + 1
            lease_until = now + timedelta(seconds=lease_seconds)
            lease.update(
                {
                    "active_job_id": selected.job_id,
                    "owner_id": worker_id,
                    "lease_until": lease_until,
                    "fencing_token": fencing_token,
                }
            )
            claimed = selected.model_copy(
                update={
                    "status": LifecycleJobStatus.RUNNING,
                    "owner_id": worker_id,
                    "lease_until": lease_until,
                    "fencing_token": fencing_token,
                    "attempts": selected.attempts + 1,
                    "started_at": selected.started_at or now,
                    "updated_at": now,
                }
            )
            self._jobs[claimed.job_id] = claimed
            return self._copy(claimed)

    def _owns(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        lease = self._leases[(job.aggregate_type, job.aggregate_id)]
        return (
            lease["active_job_id"] == job_id
            and lease["owner_id"] == worker_id
            and lease["fencing_token"] == fencing_token
            and job.owner_id == worker_id
            and job.fencing_token == fencing_token
        )

    def _release(self, job: LifecycleJob) -> None:
        lease = self._leases[(job.aggregate_type, job.aggregate_id)]
        lease.update({"active_job_id": None, "owner_id": None, "lease_until": None})

    def heartbeat(
        self, job_id: str, worker_id: str, fencing_token: int, *, lease_seconds: int
    ) -> bool:
        now = self._clock()
        with self._lock:
            if not self._owns(job_id, worker_id, fencing_token):
                return False
            job = self._jobs[job_id]
            lease = self._leases[(job.aggregate_type, job.aggregate_id)]
            if lease["lease_until"] is None or lease["lease_until"] <= now:
                return False
            if job.status != LifecycleJobStatus.RUNNING:
                return False
            lease_until = now + timedelta(seconds=lease_seconds)
            self._leases[(job.aggregate_type, job.aggregate_id)]["lease_until"] = lease_until
            self._jobs[job_id] = job.model_copy(
                update={"lease_until": lease_until, "updated_at": now}
            )
            return True

    def can_continue(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        now = self._clock()
        with self._lock:
            if not self._owns(job_id, worker_id, fencing_token):
                return False
            job = self._jobs[job_id]
            lease = self._leases[(job.aggregate_type, job.aggregate_id)]
            return bool(
                job.status == LifecycleJobStatus.RUNNING
                and lease["lease_until"] is not None
                and lease["lease_until"] > now
            )

    def checkpoint(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        step: str,
        evidence: dict | None = None,
    ) -> bool:
        now = self._clock()
        with self._lock:
            if not self._owns(job_id, worker_id, fencing_token):
                return False
            job = self._jobs[job_id]
            if job.status != LifecycleJobStatus.RUNNING:
                return False
            self._jobs[job_id] = job.model_copy(
                update={
                    "step": step,
                    "evidence": {**job.evidence, **(evidence or {})},
                    "updated_at": now,
                }
            )
            return True

    def complete(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        now = self._clock()
        with self._lock:
            if not self._owns(job_id, worker_id, fencing_token):
                return False
            job = self._jobs[job_id]
            if job.status != LifecycleJobStatus.RUNNING:
                return False
            completed = job.model_copy(
                update={
                    "status": LifecycleJobStatus.SUCCEEDED,
                    "step": "completed",
                    "owner_id": None,
                    "lease_until": None,
                    "updated_at": now,
                    "completed_at": now,
                }
            )
            self._jobs[job_id] = completed
            self._release(job)
            return True

    def fail(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        error: str,
        retry_delay_seconds: int,
    ) -> bool:
        now = self._clock()
        with self._lock:
            if not self._owns(job_id, worker_id, fencing_token):
                return False
            job = self._jobs[job_id]
            if job.status == LifecycleJobStatus.CANCEL_REQUESTED:
                return self.acknowledge_cancel(job_id, worker_id, fencing_token)
            if job.status != LifecycleJobStatus.RUNNING:
                return False
            terminal = job.attempts >= job.max_attempts
            failed = job.model_copy(
                update={
                    "status": (
                        LifecycleJobStatus.FAILED if terminal else LifecycleJobStatus.QUEUED
                    ),
                    "last_error": error,
                    "owner_id": None,
                    "lease_until": None,
                    "next_attempt_at": now + timedelta(seconds=retry_delay_seconds),
                    "updated_at": now,
                    "completed_at": now if terminal else None,
                }
            )
            self._jobs[job_id] = failed
            self._release(job)
            return True

    def request_cancel(self, job_id: str) -> bool:
        now = self._clock()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in TERMINAL_LIFECYCLE_JOB_STATUSES:
                return False
            if job.status == LifecycleJobStatus.QUEUED:
                status = LifecycleJobStatus.CANCELLED
                completed_at = now
            else:
                status = LifecycleJobStatus.CANCEL_REQUESTED
                completed_at = None
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": status,
                    "completed_at": completed_at,
                    "updated_at": now,
                }
            )
            return True

    def request_cancel_for_aggregate(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        operations: set[LifecycleJobOperation],
    ) -> int:
        with self._lock:
            job_ids = [
                job.job_id
                for job in self._jobs.values()
                if job.aggregate_type == aggregate_type
                and job.aggregate_id == aggregate_id
                and job.operation in operations
                and job.status
                in {LifecycleJobStatus.QUEUED, LifecycleJobStatus.RUNNING}
            ]
            return sum(self.request_cancel(job_id) for job_id in job_ids)

    def acknowledge_cancel(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        now = self._clock()
        with self._lock:
            if not self._owns(job_id, worker_id, fencing_token):
                return False
            job = self._jobs[job_id]
            if job.status != LifecycleJobStatus.CANCEL_REQUESTED:
                return False
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": LifecycleJobStatus.CANCELLED,
                    "owner_id": None,
                    "lease_until": None,
                    "completed_at": now,
                    "updated_at": now,
                }
            )
            self._release(job)
            return True

    def is_cancel_requested(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        with self._lock:
            return (
                self._owns(job_id, worker_id, fencing_token)
                and self._jobs[job_id].status == LifecycleJobStatus.CANCEL_REQUESTED
            )


_JOB_COLUMNS = (
    "job_id, operation, aggregate_type, aggregate_id, cluster_ref, status, "
    "priority, idempotency_key, payload, step, evidence, attempts, max_attempts, "
    "owner_id, lease_until, fencing_token, next_attempt_at, last_error, "
    "created_at, updated_at, started_at, completed_at"
)


def _job_from_row(row) -> LifecycleJob | None:
    if not row:
        return None
    values = dict(zip(_JOB_COLUMNS.split(", "), row))
    values["payload"] = (
        json.loads(values["payload"]) if isinstance(values["payload"], str) else values["payload"]
    )
    values["evidence"] = (
        json.loads(values["evidence"])
        if isinstance(values["evidence"], str)
        else values["evidence"]
    )
    return LifecycleJob.model_validate(values)


class PostgresLifecycleJobStore:
    """PostgreSQL queue with row leases and monotonically increasing fences."""

    def enqueue(self, job: LifecycleJob) -> LifecycleJob:
        conn = _get_sync_conn()
        if not conn:
            raise PersistenceUnavailableError("lifecycle jobs require PostgreSQL")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO lifecycle_aggregate_leases
                       (aggregate_type, aggregate_id)
                       VALUES (%s, %s) ON CONFLICT DO NOTHING""",
                    (job.aggregate_type, job.aggregate_id),
                )
                cur.execute(
                    f"""INSERT INTO lifecycle_jobs
                       ({_JOB_COLUMNS})
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                               %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s, %s)
                       ON CONFLICT (idempotency_key) DO NOTHING
                       RETURNING {_JOB_COLUMNS}""",
                    (
                        job.job_id,
                        job.operation.value,
                        job.aggregate_type,
                        job.aggregate_id,
                        job.cluster_ref,
                        job.status.value,
                        job.priority,
                        job.idempotency_key,
                        json.dumps(job.payload),
                        job.step,
                        json.dumps(job.evidence),
                        job.attempts,
                        job.max_attempts,
                        job.owner_id,
                        job.lease_until,
                        job.fencing_token,
                        job.next_attempt_at,
                        job.last_error,
                        job.created_at,
                        job.updated_at,
                        job.started_at,
                        job.completed_at,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        f"SELECT {_JOB_COLUMNS} FROM lifecycle_jobs WHERE idempotency_key = %s",
                        (job.idempotency_key,),
                    )
                    row = cur.fetchone()
            conn.commit()
            return _job_from_row(row)
        except Exception as exc:
            conn.rollback()
            raise PersistenceUnavailableError("failed to enqueue lifecycle job") from exc
        finally:
            conn.close()

    def get(self, job_id: str) -> LifecycleJob | None:
        conn = _get_sync_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_JOB_COLUMNS} FROM lifecycle_jobs WHERE job_id = %s",
                    (job_id,),
                )
                return _job_from_row(cur.fetchone())
        finally:
            conn.close()

    def list_all(self) -> list[LifecycleJob]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {_JOB_COLUMNS} FROM lifecycle_jobs ORDER BY created_at")
                return [_job_from_row(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def claim_next(self, worker_id: str, *, lease_seconds: int) -> LifecycleJob | None:
        conn = _get_sync_conn()
        if not conn:
            raise PersistenceUnavailableError("lifecycle jobs require PostgreSQL")
        try:
            with conn.cursor() as cur:
                # A cancellation can outlive its worker. Close it only after
                # that worker's lease has expired, then release the aggregate
                # so the higher-priority reclaim can take ownership.
                cur.execute(
                    """UPDATE lifecycle_aggregate_leases l
                       SET active_job_id = NULL, owner_id = NULL,
                           lease_until = NULL, updated_at = NOW()
                       FROM lifecycle_jobs j
                       WHERE j.status = 'cancel_requested'
                         AND j.lease_until <= NOW()
                         AND l.active_job_id = j.job_id
                         AND l.fencing_token = j.fencing_token"""
                )
                cur.execute(
                    """UPDATE lifecycle_jobs
                       SET status = 'cancelled', owner_id = NULL,
                           lease_until = NULL, completed_at = NOW(),
                           updated_at = NOW()
                       WHERE status = 'cancel_requested'
                         AND lease_until <= NOW()"""
                )
                cur.execute(
                    """SELECT j.job_id, j.aggregate_type, j.aggregate_id
                       FROM lifecycle_jobs j
                       JOIN lifecycle_aggregate_leases l
                         ON l.aggregate_type = j.aggregate_type
                        AND l.aggregate_id = j.aggregate_id
                       WHERE j.next_attempt_at <= NOW()
                         AND (j.status = 'queued'
                              OR (j.status = 'running' AND j.lease_until <= NOW()))
                         AND (l.lease_until IS NULL OR l.lease_until <= NOW())
                       ORDER BY j.priority, j.next_attempt_at, j.created_at, j.job_id
                       FOR UPDATE OF l SKIP LOCKED
                       LIMIT 1"""
                )
                candidate = cur.fetchone()
                if not candidate:
                    conn.commit()
                    return None
                job_id, aggregate_type, aggregate_id = candidate
                cur.execute(
                    """UPDATE lifecycle_aggregate_leases
                       SET active_job_id = %s,
                           owner_id = %s,
                           lease_until = NOW() + (%s * INTERVAL '1 second'),
                           fencing_token = fencing_token + 1,
                           updated_at = NOW()
                       WHERE aggregate_type = %s AND aggregate_id = %s
                       RETURNING fencing_token, lease_until""",
                    (job_id, worker_id, lease_seconds, aggregate_type, aggregate_id),
                )
                fencing_token, lease_until = cur.fetchone()
                cur.execute(
                    f"""UPDATE lifecycle_jobs
                       SET status = 'running', owner_id = %s, lease_until = %s,
                           fencing_token = %s, attempts = attempts + 1,
                           started_at = COALESCE(started_at, NOW()), updated_at = NOW()
                       WHERE job_id = %s
                       RETURNING {_JOB_COLUMNS}""",
                    (worker_id, lease_until, fencing_token, job_id),
                )
                claimed = _job_from_row(cur.fetchone())
            conn.commit()
            return claimed
        except Exception as exc:
            conn.rollback()
            raise PersistenceUnavailableError("failed to claim lifecycle job") from exc
        finally:
            conn.close()

    def _owned_job(self, cur, job_id: str, worker_id: str, fencing_token: int):
        qualified_columns = ", ".join(
            f"j.{column}" for column in _JOB_COLUMNS.split(", ")
        )
        cur.execute(
            f"""SELECT {qualified_columns}
                FROM lifecycle_jobs j
                JOIN lifecycle_aggregate_leases l
                  ON l.aggregate_type = j.aggregate_type
                 AND l.aggregate_id = j.aggregate_id
                WHERE j.job_id = %s
                  AND j.owner_id = %s
                  AND j.fencing_token = %s
                  AND l.active_job_id = j.job_id
                  AND l.owner_id = %s
                  AND l.fencing_token = %s
                  AND l.lease_until > NOW()
                FOR UPDATE OF j, l""",
            (job_id, worker_id, fencing_token, worker_id, fencing_token),
        )
        return _job_from_row(cur.fetchone())

    @staticmethod
    def _release(cur, job: LifecycleJob) -> None:
        cur.execute(
            """UPDATE lifecycle_aggregate_leases
               SET active_job_id = NULL, owner_id = NULL, lease_until = NULL,
                   updated_at = NOW()
               WHERE aggregate_type = %s AND aggregate_id = %s
                 AND active_job_id = %s AND fencing_token = %s""",
            (job.aggregate_type, job.aggregate_id, job.job_id, job.fencing_token),
        )

    def heartbeat(
        self, job_id: str, worker_id: str, fencing_token: int, *, lease_seconds: int
    ) -> bool:
        return self._mutate_owned(
            job_id,
            worker_id,
            fencing_token,
            lambda cur, job: self._heartbeat(cur, job, lease_seconds),
        )

    def can_continue(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        conn = _get_sync_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1
                       FROM lifecycle_jobs j
                       JOIN lifecycle_aggregate_leases l
                         ON l.aggregate_type = j.aggregate_type
                        AND l.aggregate_id = j.aggregate_id
                       WHERE j.job_id = %s
                         AND j.status = 'running'
                         AND j.owner_id = %s
                         AND j.fencing_token = %s
                         AND j.lease_until > NOW()
                         AND l.active_job_id = j.job_id
                         AND l.owner_id = %s
                         AND l.fencing_token = %s
                         AND l.lease_until > NOW()""",
                    (job_id, worker_id, fencing_token, worker_id, fencing_token),
                )
                return cur.fetchone() is not None
        except Exception as exc:
            raise PersistenceUnavailableError(
                "failed to verify lifecycle ownership"
            ) from exc
        finally:
            conn.close()

    @staticmethod
    def _heartbeat(cur, job: LifecycleJob, lease_seconds: int) -> bool:
        if job.status != LifecycleJobStatus.RUNNING:
            return False
        cur.execute(
            """UPDATE lifecycle_aggregate_leases
               SET lease_until = NOW() + (%s * INTERVAL '1 second'), updated_at = NOW()
               WHERE aggregate_type = %s AND aggregate_id = %s
                 AND active_job_id = %s AND fencing_token = %s
               RETURNING lease_until""",
            (
                lease_seconds,
                job.aggregate_type,
                job.aggregate_id,
                job.job_id,
                job.fencing_token,
            ),
        )
        row = cur.fetchone()
        if not row:
            return False
        cur.execute(
            "UPDATE lifecycle_jobs SET lease_until = %s, updated_at = NOW() WHERE job_id = %s",
            (row[0], job.job_id),
        )
        return True

    def checkpoint(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        step: str,
        evidence: dict | None = None,
    ) -> bool:
        def mutation(cur, job: LifecycleJob) -> bool:
            if job.status != LifecycleJobStatus.RUNNING:
                return False
            cur.execute(
                """UPDATE lifecycle_jobs
                   SET step = %s, evidence = evidence || %s::jsonb, updated_at = NOW()
                   WHERE job_id = %s""",
                (step, json.dumps(evidence or {}), job.job_id),
            )
            return True

        return self._mutate_owned(job_id, worker_id, fencing_token, mutation)

    def complete(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        def mutation(cur, job: LifecycleJob) -> bool:
            if job.status != LifecycleJobStatus.RUNNING:
                return False
            cur.execute(
                """UPDATE lifecycle_jobs SET status = 'succeeded', step = 'completed',
                       owner_id = NULL, lease_until = NULL, completed_at = NOW(),
                       updated_at = NOW() WHERE job_id = %s""",
                (job.job_id,),
            )
            self._release(cur, job)
            return True

        return self._mutate_owned(job_id, worker_id, fencing_token, mutation)

    def fail(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        *,
        error: str,
        retry_delay_seconds: int,
    ) -> bool:
        def mutation(cur, job: LifecycleJob) -> bool:
            if job.status == LifecycleJobStatus.CANCEL_REQUESTED:
                return self._acknowledge_cancel(cur, job)
            if job.status != LifecycleJobStatus.RUNNING:
                return False
            terminal = job.attempts >= job.max_attempts
            cur.execute(
                """UPDATE lifecycle_jobs
                   SET status = %s, last_error = %s, owner_id = NULL,
                       lease_until = NULL,
                       next_attempt_at = NOW() + (%s * INTERVAL '1 second'),
                       completed_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                       updated_at = NOW()
                   WHERE job_id = %s""",
                (
                    "failed" if terminal else "queued",
                    error,
                    retry_delay_seconds,
                    terminal,
                    job.job_id,
                ),
            )
            self._release(cur, job)
            return True

        return self._mutate_owned(job_id, worker_id, fencing_token, mutation)

    def request_cancel(self, job_id: str) -> bool:
        conn = _get_sync_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE lifecycle_jobs
                       SET status = CASE WHEN status = 'queued'
                                         THEN 'cancelled' ELSE 'cancel_requested' END,
                           completed_at = CASE WHEN status = 'queued'
                                               THEN NOW() ELSE completed_at END,
                           updated_at = NOW()
                       WHERE job_id = %s
                         AND status IN ('queued', 'running')
                       RETURNING job_id""",
                    (job_id,),
                )
                changed = cur.fetchone() is not None
            conn.commit()
            return changed
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def request_cancel_for_aggregate(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        operations: set[LifecycleJobOperation],
    ) -> int:
        if not operations:
            return 0
        conn = _get_sync_conn()
        if not conn:
            return 0
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE lifecycle_jobs
                       SET status = CASE WHEN status = 'queued'
                                         THEN 'cancelled' ELSE 'cancel_requested' END,
                           completed_at = CASE WHEN status = 'queued'
                                               THEN NOW() ELSE completed_at END,
                           updated_at = NOW()
                       WHERE aggregate_type = %s
                         AND aggregate_id = %s
                         AND operation = ANY(%s)
                         AND status IN ('queued', 'running')
                       RETURNING job_id""",
                    (
                        aggregate_type,
                        aggregate_id,
                        [operation.value for operation in operations],
                    ),
                )
                changed = len(cur.fetchall())
            conn.commit()
            return changed
        except Exception as exc:
            conn.rollback()
            raise PersistenceUnavailableError(
                "failed to cancel lifecycle jobs for aggregate"
            ) from exc
        finally:
            conn.close()

    def acknowledge_cancel(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        return self._mutate_owned(
            job_id,
            worker_id,
            fencing_token,
            lambda cur, job: self._acknowledge_cancel(cur, job),
        )

    def _acknowledge_cancel(self, cur, job: LifecycleJob) -> bool:
        if job.status != LifecycleJobStatus.CANCEL_REQUESTED:
            return False
        cur.execute(
            """UPDATE lifecycle_jobs SET status = 'cancelled', owner_id = NULL,
                   lease_until = NULL, completed_at = NOW(), updated_at = NOW()
               WHERE job_id = %s""",
            (job.job_id,),
        )
        self._release(cur, job)
        return True

    def is_cancel_requested(self, job_id: str, worker_id: str, fencing_token: int) -> bool:
        job = self.get(job_id)
        return bool(
            job
            and job.owner_id == worker_id
            and job.fencing_token == fencing_token
            and job.status == LifecycleJobStatus.CANCEL_REQUESTED
        )

    def _mutate_owned(self, job_id, worker_id, fencing_token, mutation) -> bool:
        conn = _get_sync_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                job = self._owned_job(cur, job_id, worker_id, fencing_token)
                changed = bool(job and mutation(cur, job))
            conn.commit()
            return changed
        except Exception as exc:
            conn.rollback()
            raise PersistenceUnavailableError("failed to mutate lifecycle job") from exc
        finally:
            conn.close()
