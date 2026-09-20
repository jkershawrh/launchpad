"""Deterministic event-to-workshop lifecycle orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.domain.access import ExposurePolicy
from app.domain.enums import SessionStatus, WorkshopSeatStatus, WorkshopStatus
from app.domain.events import (
    EventCapacityReservation,
    EventCleanupEvidenceResult,
    EventCleanupSummary,
    EventCleanupWorkshopEvidence,
    EventRecord,
    EventStatusResult,
    EventStatusSummary,
    EventWorkshopLaunchItem,
    EventWorkshopLaunchRequest,
    EventWorkshopLaunchResult,
    EventWorkshopPublicAccessResult,
    EventWorkshopReclaimItem,
    EventWorkshopReclaimResult,
    EventWorkshopStatusItem,
)
from app.domain.lifecycle_jobs import LifecycleJobOperation, LifecycleJobStatus
from app.services.event_reservations import EventReservationLedger
from app.services.lifecycle_worker import LifecycleQueueService
from app.services.provisioning import ProvisioningService
from app.services.public_access import PublicAccessService


class EventOrchestrationConflictError(RuntimeError):
    """The immutable event, reservations, and launch request do not agree."""


class EventOrchestrationService:
    """Consume every event hold and enqueue bounded lifecycle work.

    Public access remains deliberately inactive. Instructor codes are issued
    only after the workshops are ready, so a partial launch cannot disclose a
    one-time secret that is then lost before the response reaches the caller.
    """

    def __init__(
        self,
        *,
        reservation_ledger: EventReservationLedger,
        provisioning: ProvisioningService,
        lifecycle_queue: LifecycleQueueService,
        public_access: PublicAccessService | None = None,
    ) -> None:
        self.reservation_ledger = reservation_ledger
        self.provisioning = provisioning
        self.lifecycle_queue = lifecycle_queue
        self.public_access = public_access

    def launch(
        self,
        record: EventRecord,
        request: EventWorkshopLaunchRequest,
    ) -> EventWorkshopLaunchResult:
        manifest = record.manifest
        reservations = self.reservation_ledger.list_for_event(manifest.event_id)
        self._validate_complete_plan(record, reservations)

        exposure = ExposurePolicy(manifest.exposure_policy)
        items: list[EventWorkshopLaunchItem] = []
        for reservation in reservations:
            order = self.provisioning.create_reserved_workshop_order(
                reservation,
                tenant_id=request.tenant_id,
                exposure_policy=exposure,
                ttl=f"{manifest.retention.hours}h",
            )
            existing_tenant = order.metadata.get("event_tenant_id")
            if existing_tenant and existing_tenant != request.tenant_id:
                raise EventOrchestrationConflictError(
                    "Event workshop is already bound to a different tenant"
                )
            if not existing_tenant:
                order = order.model_copy(
                    update={
                        "metadata": {
                            **order.metadata,
                            "event_tenant_id": request.tenant_id,
                            "public_access_state": (
                                "pending_activation"
                                if exposure == ExposurePolicy.PUBLIC_CODE
                                else "not_required"
                            ),
                        }
                    }
                )
                self.provisioning._save_workshop(order)

            queued = self.provisioning.queue_workshop(order.workshop_id)
            job = self.lifecycle_queue.enqueue_workshop_provision(queued)
            if queued.metadata.get("lifecycle_job_id") != job.job_id:
                queued = queued.model_copy(
                    update={
                        "metadata": {
                            **queued.metadata,
                            "lifecycle_job_id": job.job_id,
                        }
                    }
                )
                self.provisioning._save_workshop(queued)
            items.append(
                EventWorkshopLaunchItem(
                    reservation_id=reservation.reservation_id,
                    cohort_id=reservation.cohort_id,
                    lab_ref=reservation.lab_ref,
                    workshop_id=queued.workshop_id,
                    lifecycle_job_id=job.job_id,
                    cluster_ref=reservation.cluster_ref,
                    catalog_id=reservation.catalog_id,
                    catalog_release=reservation.catalog_release,
                    seats=reservation.resources.seats,
                )
            )

        return EventWorkshopLaunchResult(
            event_id=manifest.event_id,
            tenant_id=request.tenant_id,
            public_access_state=(
                "pending_activation"
                if exposure == ExposurePolicy.PUBLIC_CODE
                else "not_required"
            ),
            workshops=items,
        )

    def activate_public_access(
        self,
        record: EventRecord,
        workshop_id: str,
    ) -> EventWorkshopPublicAccessResult:
        """Issue one workshop code only after every reserved seat is ready."""

        if self.public_access is None:
            raise ValueError("Public access service is unavailable")
        workshop = self.provisioning.get_workshop(workshop_id)
        if workshop is None or workshop.metadata.get("event_id") != record.manifest.event_id:
            raise EventOrchestrationConflictError(
                "Workshop does not belong to the approved event"
            )
        if (
            record.manifest.exposure_policy != ExposurePolicy.PUBLIC_CODE.value
            or workshop.exposure_policy != ExposurePolicy.PUBLIC_CODE
        ):
            raise EventOrchestrationConflictError(
                "Workshop is not approved for public access"
            )
        try:
            self.provisioning._validate_reserved_workshop_binding(workshop)
        except ValueError as exc:
            raise EventOrchestrationConflictError(str(exc)) from exc
        if self.public_access.get_policy(workshop_id) is not None:
            raise EventOrchestrationConflictError(
                "Public access is already activated; rotate the code if it was lost"
            )
        if workshop.status not in {WorkshopStatus.READY, WorkshopStatus.ACTIVE}:
            raise EventOrchestrationConflictError("Workshop is not fully ready")
        if len(workshop.seats) != workshop.num_users or any(
            seat.status not in {WorkshopSeatStatus.READY, WorkshopSeatStatus.ACTIVE}
            or not seat.session_id
            for seat in workshop.seats
        ):
            raise EventOrchestrationConflictError("Workshop is not fully ready")
        if len({seat.session_id for seat in workshop.seats}) != workshop.num_users:
            raise EventOrchestrationConflictError(
                "Workshop seat lifecycle evidence is incomplete"
            )

        sessions = [
            self.provisioning.get_session(seat.session_id)
            for seat in workshop.seats
        ]
        if any(
            session is None
            or session.cluster_ref != workshop.cluster_ref
            or session.expires_at is None
            for session in sessions
        ):
            raise EventOrchestrationConflictError(
                "Workshop seat lifecycle evidence is incomplete"
            )
        expires_at = min(session.expires_at for session in sessions if session)
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
        if expires_at <= datetime.now(UTC).replace(tzinfo=None):
            raise EventOrchestrationConflictError(
                "Workshop public access expiration has already passed"
            )
        policy, plaintext = self.public_access.create_policy(
            order_id=workshop.workshop_id,
            order_type="workshop",
            catalog_slug=workshop.catalog_item_id,
            seat_refs=[seat.seat_id for seat in workshop.seats],
            expires_at=expires_at,
        )
        updated = workshop.model_copy(
            update={
                "public_url": policy.public_url,
                "metadata": {
                    **workshop.metadata,
                    "public_access_state": "active",
                    "public_access_code_version": policy.code_version,
                },
            }
        )
        self.provisioning._save_workshop(updated)
        return EventWorkshopPublicAccessResult(
            event_id=record.manifest.event_id,
            workshop_id=workshop.workshop_id,
            public_url=policy.public_url,
            one_time_access_code=plaintext,
            expires_at=policy.expires_at,
        )

    def status(self, record: EventRecord) -> EventStatusResult:
        """Join durable event records without mutating lifecycle state."""

        reservations = self.reservation_ledger.list_for_event(
            record.manifest.event_id
        )
        expected = {
            (
                item.cohort_id,
                item.lab_ref,
                item.catalog_id,
                item.catalog_release,
                item.cluster_id,
                item.seats,
            )
            for item in record.capacity_preview.allocations
        }
        actual = {
            (
                item.cohort_id,
                item.lab_ref,
                item.catalog_id,
                item.catalog_release,
                item.cluster_ref,
                item.resources.seats,
            )
            for item in reservations
        }
        reservation_complete = expected == actual and len(reservations) == len(expected)
        jobs = {job.job_id: job for job in self.lifecycle_queue.list_all()}
        rows: list[EventWorkshopStatusItem] = []
        terminal_failures = False
        completed = 0
        public_active = 0
        for reservation in reservations:
            workshop = (
                self.provisioning.get_workshop(reservation.workshop_id)
                if reservation.workshop_id
                else None
            )
            job_id = (
                str(workshop.metadata.get("lifecycle_job_id", "")) or None
                if workshop
                else None
            )
            job = jobs.get(job_id) if job_id else None
            seats = workshop.seats if workshop else []
            ready_seats = sum(
                seat.status in {WorkshopSeatStatus.READY, WorkshopSeatStatus.ACTIVE}
                for seat in seats
            )
            failed_seats = sum(
                seat.status == WorkshopSeatStatus.FAILED for seat in seats
            )
            reclaimed_seats = sum(
                seat.status == WorkshopSeatStatus.RECLAIMED for seat in seats
            )
            if record.manifest.exposure_policy == ExposurePolicy.INTERNAL.value:
                public_state = "not_required"
                public_url = None
            else:
                policy = (
                    self.public_access.get_policy(workshop.workshop_id)
                    if self.public_access and workshop
                    else None
                )
                if policy and policy.enabled:
                    public_state = "active"
                    public_url = policy.public_url
                    public_active += 1
                elif policy:
                    public_state = "disabled"
                    public_url = policy.public_url
                else:
                    public_state = "pending_activation"
                    public_url = workshop.public_url if workshop else None

            workshop_status = workshop.status.value if workshop else None
            job_status = job.status.value if job else None
            if workshop and workshop.status in {
                WorkshopStatus.FAILED,
                WorkshopStatus.PREFLIGHT_FAILED,
                WorkshopStatus.COMPLETED_WITH_ERRORS,
            }:
                terminal_failures = True
            if job_status == "failed" or failed_seats:
                terminal_failures = True
            if workshop and workshop.status == WorkshopStatus.COMPLETED:
                completed += 1
            rows.append(
                EventWorkshopStatusItem(
                    reservation_id=reservation.reservation_id,
                    cohort_id=reservation.cohort_id,
                    lab_ref=reservation.lab_ref,
                    catalog_id=reservation.catalog_id,
                    catalog_release=reservation.catalog_release,
                    cluster_ref=reservation.cluster_ref,
                    seats=reservation.resources.seats,
                    reservation_status=reservation.status,
                    workshop_id=reservation.workshop_id,
                    workshop_status=workshop_status,
                    lifecycle_job_id=job_id,
                    lifecycle_job_status=job_status,
                    ready_seats=ready_seats,
                    failed_seats=failed_seats,
                    reclaimed_seats=reclaimed_seats,
                    public_access_state=public_state,
                    public_url=public_url,
                )
            )

        workshop_count = sum(item.workshop_id is not None for item in rows)
        all_released = bool(rows) and all(
            item.reservation_status == "released" for item in rows
        )
        reservation_state_problem = any(
            item.reservation_status == "expired"
            or (item.reservation_status == "released" and not all_released)
            for item in rows
        )
        ready_workshops = sum(
            item.workshop_status in {WorkshopStatus.READY.value, WorkshopStatus.ACTIVE.value}
            for item in rows
        )
        required_public = (
            workshop_count
            if record.manifest.exposure_policy == ExposurePolicy.PUBLIC_CODE.value
            else 0
        )
        if not reservations:
            state = "approved"
        elif not reservation_complete or reservation_state_problem or terminal_failures:
            state = "attention_required"
        elif all_released:
            state = "released"
        elif completed == len(expected) and completed:
            state = "cleanup_evidence_pending"
        elif ready_workshops == len(expected) and ready_workshops:
            state = (
                "ready"
                if public_active == required_public
                else "awaiting_public_access"
            )
        elif workshop_count:
            state = "progressing"
        else:
            state = "reserved"

        return EventStatusResult(
            event_id=record.manifest.event_id,
            state=state,
            reservation_complete=reservation_complete,
            summary=EventStatusSummary(
                reservations=len(reservations),
                workshops=workshop_count,
                lifecycle_jobs=sum(item.lifecycle_job_id is not None for item in rows),
                seats=sum(item.seats for item in rows),
                ready_seats=sum(item.ready_seats for item in rows),
                failed_seats=sum(item.failed_seats for item in rows),
                reclaimed_seats=sum(item.reclaimed_seats for item in rows),
                public_workshops_active=public_active,
            ),
            workshops=rows,
        )

    def reclaim(self, record: EventRecord) -> EventWorkshopReclaimResult:
        """Disable event access, then queue cleanup on persisted clusters."""

        reservations = self.reservation_ledger.list_for_event(
            record.manifest.event_id
        )
        self._validate_complete_plan(record, reservations)
        public_event = (
            record.manifest.exposure_policy == ExposurePolicy.PUBLIC_CODE.value
        )
        if public_event and self.public_access is None:
            raise ValueError("Public access service is unavailable")

        bound = []
        for reservation in reservations:
            if reservation.status != "consumed" or not reservation.workshop_id:
                raise EventOrchestrationConflictError(
                    "Every event reservation must be consumed before reclaim"
                )
            workshop = self.provisioning.get_workshop(reservation.workshop_id)
            if workshop is None or workshop.metadata.get("event_id") != record.manifest.event_id:
                raise EventOrchestrationConflictError(
                    "Event workshop binding is incomplete"
                )
            try:
                self.provisioning._validate_reserved_workshop_binding(workshop)
            except ValueError as exc:
                raise EventOrchestrationConflictError(str(exc)) from exc
            bound.append((reservation, workshop))

        # Access denial is event-wide and precedes the first cleanup mutation.
        if self.public_access:
            for _reservation, workshop in bound:
                self.public_access.expire_order(workshop.workshop_id)

        items = []
        for reservation, workshop in bound:
            queued = self.provisioning.queue_workshop_reclaim(workshop.workshop_id)
            job = self.lifecycle_queue.enqueue_workshop_reclaim(queued)
            public_state = "disabled" if public_event else "not_required"
            metadata = {
                **queued.metadata,
                "lifecycle_job_id": job.job_id,
                "public_access_state": public_state,
            }
            if queued.metadata != metadata:
                queued = queued.model_copy(update={"metadata": metadata})
                self.provisioning._save_workshop(queued)
            items.append(
                EventWorkshopReclaimItem(
                    reservation_id=reservation.reservation_id,
                    workshop_id=workshop.workshop_id,
                    lifecycle_job_id=job.job_id,
                    cluster_ref=reservation.cluster_ref,
                    public_access_state=public_state,
                )
            )

        return EventWorkshopReclaimResult(
            event_id=record.manifest.event_id,
            workshops=items,
        )

    def finalize_cleanup(self, record: EventRecord) -> EventCleanupEvidenceResult:
        """Release capacity only after complete, read-only zero-residue proof."""

        reservations = self.reservation_ledger.list_for_event(
            record.manifest.event_id
        )
        if (
            record.manifest.exposure_policy == ExposurePolicy.PUBLIC_CODE.value
            and self.public_access is None
        ):
            raise EventOrchestrationConflictError(
                "Public access cleanup inspection is unavailable"
            )
        if not self._plan_matches(record, reservations):
            raise EventOrchestrationConflictError(
                "Event does not have a complete reservation plan"
            )
        released = [item for item in reservations if item.status == "released"]
        if released and len(released) != len(reservations):
            raise EventOrchestrationConflictError(
                "Event reservations have a partial release state"
            )
        if any(not item.workshop_id for item in reservations):
            raise EventOrchestrationConflictError(
                "Every event reservation must have a workshop binding"
            )

        jobs = {job.job_id: job for job in self.lifecycle_queue.list_all()}
        rows: list[EventCleanupWorkshopEvidence] = []
        failures: list[str] = []
        total_active_entitlements = 0
        total_identities_due_disable = 0
        for reservation in reservations:
            workshop = self.provisioning.get_workshop(reservation.workshop_id)
            if (
                workshop is None
                or workshop.metadata.get("event_id") != record.manifest.event_id
                or workshop.cluster_ref != reservation.cluster_ref
            ):
                failures.append(f"{reservation.reservation_id}: workshop binding")
                continue
            job_id = str(workshop.metadata.get("lifecycle_job_id", ""))
            job = jobs.get(job_id)
            if (
                job is None
                or job.operation != LifecycleJobOperation.RECLAIM_WORKSHOP
                or job.status != LifecycleJobStatus.SUCCEEDED
                or job.cluster_ref != reservation.cluster_ref
            ):
                failures.append(f"{workshop.workshop_id}: reclaim job")
            if workshop.status != WorkshopStatus.COMPLETED:
                failures.append(f"{workshop.workshop_id}: workshop status")
            if len(workshop.seats) != workshop.num_users or any(
                seat.status != WorkshopSeatStatus.RECLAIMED
                for seat in workshop.seats
            ):
                failures.append(f"{workshop.workshop_id}: seat cleanup")

            external_residue = 0
            residue_counts = {
                "namespace": 0,
                "image_puller_role_binding": 0,
                "showroom_application": 0,
                "workload_application": 0,
                "credentials": 0,
            }
            session_count = 0
            for seat in workshop.seats:
                if not seat.session_id:
                    continue
                session_count += 1
                session = self.provisioning.get_session(seat.session_id)
                if session is None or session.status != SessionStatus.RECLAIMED:
                    failures.append(f"{seat.seat_id}: session cleanup")
                    continue
                try:
                    residue = self.provisioning.inspect_session_cleanup(
                        session.session_id
                    )
                except Exception:  # noqa: BLE001 - evidence gates must fail closed
                    failures.append(f"{seat.seat_id}: residue inspection")
                    continue
                for key, value in residue.items():
                    residue_counts[key] = residue_counts.get(key, 0) + value
                external_residue += sum(residue.values())

            access_state = (
                self.public_access.cleanup_state(workshop.workshop_id)
                if self.public_access
                else {
                    "policy_enabled": 0,
                    "active_entitlements": 0,
                    "identities_due_disable": 0,
                }
            )
            access_residue = sum(access_state.values())
            total_active_entitlements += access_state["active_entitlements"]
            total_identities_due_disable += access_state["identities_due_disable"]
            if external_residue:
                failures.append(f"{workshop.workshop_id}: external residue")
            if access_residue:
                failures.append(f"{workshop.workshop_id}: access residue")
            rows.append(
                EventCleanupWorkshopEvidence(
                    reservation_id=reservation.reservation_id,
                    workshop_id=workshop.workshop_id,
                    lifecycle_job_id=job_id,
                    cluster_ref=reservation.cluster_ref,
                    seats=workshop.num_users,
                    sessions=session_count,
                    external_residue=external_residue,
                    access_residue=access_residue,
                    residue=residue_counts,
                    access=access_state,
                )
            )

        if failures or len(rows) != len(reservations):
            raise EventOrchestrationConflictError(
                "Zero-residue cleanup is not proven: " + ", ".join(sorted(failures))
            )
        summary = EventCleanupSummary(
            workshops=len(rows),
            seats=sum(item.seats for item in rows),
            sessions=sum(item.sessions for item in rows),
            external_residue=sum(item.external_residue for item in rows),
            access_residue=sum(item.access_residue for item in rows),
            active_entitlements=total_active_entitlements,
            identities_due_disable=total_identities_due_disable,
        )
        evidence_payload = {
            "schema_version": "launchpad.intel.com/event-cleanup/v1",
            "event_id": record.manifest.event_id,
            "summary": summary.model_dump(mode="json"),
            "workshops": [
                item.model_dump(mode="json")
                for item in sorted(rows, key=lambda value: value.reservation_id)
            ],
        }
        digest = hashlib.sha256(
            json.dumps(
                evidence_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        evidence_id = f"sha256:{digest}"
        prior_evidence = {
            item.cleanup_evidence_id for item in released if item.cleanup_evidence_id
        }
        if prior_evidence and prior_evidence != {evidence_id}:
            raise EventOrchestrationConflictError(
                "Event cleanup evidence changed after capacity release"
            )
        released_count = self.reservation_ledger.release(
            record.manifest.event_id,
            cleanup_evidence_id=evidence_id,
        )
        return EventCleanupEvidenceResult(
            event_id=record.manifest.event_id,
            cleanup_evidence_id=evidence_id,
            released_reservations=released_count,
            summary=summary,
            workshops=rows,
        )

    @staticmethod
    def _plan_matches(
        record: EventRecord,
        reservations: list[EventCapacityReservation],
    ) -> bool:
        expected = {
            (
                item.cohort_id,
                item.lab_ref,
                item.catalog_id,
                item.catalog_release,
                item.cluster_id,
                item.seats,
            )
            for item in record.capacity_preview.allocations
        }
        actual = {
            (
                item.cohort_id,
                item.lab_ref,
                item.catalog_id,
                item.catalog_release,
                item.cluster_ref,
                item.resources.seats,
            )
            for item in reservations
        }
        return expected == actual and len(reservations) == len(expected)

    @staticmethod
    def _validate_complete_plan(
        record: EventRecord,
        reservations: list[EventCapacityReservation],
    ) -> None:
        expected = {
            (
                item.cohort_id,
                item.lab_ref,
                item.catalog_id,
                item.catalog_release,
                item.cluster_id,
                item.seats,
            )
            for item in record.capacity_preview.allocations
        }
        actual = {
            (
                item.cohort_id,
                item.lab_ref,
                item.catalog_id,
                item.catalog_release,
                item.cluster_ref,
                item.resources.seats,
            )
            for item in reservations
            if item.status in {"held", "consumed"}
        }
        if expected != actual or len(reservations) != len(expected):
            raise EventOrchestrationConflictError(
                "Event does not have a complete reservation plan"
            )
        invalid = [item for item in reservations if item.status not in {"held", "consumed"}]
        if invalid:
            raise EventOrchestrationConflictError(
                "Event reservation is expired or released"
            )
