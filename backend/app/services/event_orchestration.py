"""Deterministic event-to-workshop lifecycle orchestration."""

from __future__ import annotations

from app.domain.access import ExposurePolicy
from app.domain.events import (
    EventCapacityReservation,
    EventRecord,
    EventWorkshopLaunchItem,
    EventWorkshopLaunchRequest,
    EventWorkshopLaunchResult,
)
from app.services.event_reservations import EventReservationLedger
from app.services.lifecycle_worker import LifecycleQueueService
from app.services.provisioning import ProvisioningService


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
    ) -> None:
        self.reservation_ledger = reservation_ledger
        self.provisioning = provisioning
        self.lifecycle_queue = lifecycle_queue

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
