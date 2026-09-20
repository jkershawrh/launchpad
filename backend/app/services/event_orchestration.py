"""Deterministic event-to-workshop lifecycle orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.access import ExposurePolicy
from app.domain.enums import WorkshopSeatStatus, WorkshopStatus
from app.domain.events import (
    EventCapacityReservation,
    EventRecord,
    EventWorkshopLaunchItem,
    EventWorkshopLaunchRequest,
    EventWorkshopLaunchResult,
    EventWorkshopPublicAccessResult,
)
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
