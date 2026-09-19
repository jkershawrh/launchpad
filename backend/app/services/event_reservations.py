"""Atomic event-capacity reservations with no provisioning side effects."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from app.domain.events import (
    EventCapacityReservation,
    EventCapacitySupply,
    EventRecord,
    EventReservationPlan,
    EventResourceVector,
)


class EventReservationConflictError(RuntimeError):
    """The immutable event or capacity evidence no longer matches."""


class EventReservationUnavailableError(RuntimeError):
    """The requested aggregate hold cannot fit certified remaining capacity."""


def build_event_reservation_plan(
    record: EventRecord,
    supply: EventCapacitySupply,
    *,
    expires_at: datetime,
    now: datetime | None = None,
) -> EventReservationPlan:
    """Convert an approved preview into server-owned resource holds."""

    current = now or datetime.now(UTC)
    if current.tzinfo is None or expires_at.tzinfo is None:
        raise EventReservationConflictError(
            "Reservation timestamps must include a timezone"
        )
    if expires_at <= current:
        raise EventReservationConflictError("Reservation expiration must be in the future")

    preview = record.capacity_preview
    identity = (
        preview.matrix_id,
        preview.matrix_digest,
        preview.fleet_snapshot_id,
    )
    current_identity = (
        supply.matrix_id,
        supply.matrix_digest,
        supply.fleet_snapshot_id,
    )
    if identity != current_identity:
        raise EventReservationConflictError(
            "Certified capacity evidence changed after event approval"
        )
    if not preview.eligible:
        raise EventReservationUnavailableError(
            "Approved event does not have a complete certified allocation"
        )
    if supply.fleet_snapshot_id == "not-evaluated" or supply.fleet_observed_at is None:
        raise EventReservationConflictError(
            "A fleet eligibility snapshot is required before reservation"
        )
    if supply.fleet_observed_at.tzinfo is None:
        raise EventReservationConflictError(
            "Fleet snapshot timestamp must include a timezone"
        )
    fleet_age = (current - supply.fleet_observed_at).total_seconds()
    if fleet_age > 120:
        raise EventReservationConflictError("Fleet snapshot is stale at reservation time")
    if fleet_age < -30:
        raise EventReservationConflictError(
            "Fleet snapshot is future-dated at reservation time"
        )

    clusters = {item.cluster_id: item for item in supply.clusters}
    reservations: list[EventCapacityReservation] = []
    for allocation in preview.allocations:
        cluster = clusters.get(allocation.cluster_id)
        if cluster is None or not cluster.enabled:
            raise EventReservationConflictError(
                f"Allocated cluster {allocation.cluster_id} is no longer eligible"
            )
        catalog = next(
            (
                item
                for item in cluster.catalogs
                if item.catalog_id == allocation.catalog_id
                and item.catalog_release == allocation.catalog_release
            ),
            None,
        )
        if catalog is None:
            raise EventReservationConflictError(
                "Allocated catalog release is absent from certified capacity"
            )
        if not any(catalog.resources_per_seat.model_dump().values()):
            raise EventReservationConflictError(
                "Allocated catalog release has no certified resource footprint"
            )
        resources = catalog.resources_per_seat.scaled(allocation.seats)
        resources.seats = allocation.seats
        reservations.append(
            EventCapacityReservation(
                reservation_id=(
                    f"{record.manifest.event_id}:{allocation.cohort_id}:"
                    f"{allocation.lab_ref}"
                ),
                event_id=record.manifest.event_id,
                cohort_id=allocation.cohort_id,
                lab_ref=allocation.lab_ref,
                catalog_id=allocation.catalog_id,
                catalog_release=allocation.catalog_release,
                cluster_ref=allocation.cluster_id,
                matrix_id=supply.matrix_id,
                matrix_digest=supply.matrix_digest,
                fleet_snapshot_id=supply.fleet_snapshot_id,
                resources=resources,
                expires_at=expires_at,
                created_at=current,
            )
        )

    if len(reservations) != len(preview.allocations):
        raise EventReservationConflictError("Incomplete reservation plan")
    return EventReservationPlan(
        event_id=record.manifest.event_id,
        matrix_id=supply.matrix_id,
        matrix_digest=supply.matrix_digest,
        fleet_snapshot_id=supply.fleet_snapshot_id,
        expires_at=expires_at,
        reservations=reservations,
    )


class EventReservationLedger:
    """Thread-safe local ledger or fail-closed durable-store facade."""

    def __init__(self, db_store=None) -> None:
        self._records: dict[str, EventCapacityReservation] = {}
        self._lock = Lock()
        self._db = db_store

    def reserve(
        self,
        plan: EventReservationPlan,
        supply: EventCapacitySupply,
        *,
        now: datetime | None = None,
    ) -> list[EventCapacityReservation]:
        current = now or datetime.now(UTC)
        _require_supply_identity(plan, supply)
        if self._db:
            return self._db.reserve(plan, supply, now=current)

        with self._lock:
            self._expire_locked(current)
            existing = [
                item for item in self._records.values() if item.event_id == plan.event_id
            ]
            if existing:
                if all(item.status == "held" for item in existing) and (
                    _reservation_payload(existing)
                    == _reservation_payload(plan.reservations)
                ):
                    return sorted(existing, key=lambda item: item.reservation_id)
                raise EventReservationConflictError(
                    "Event already has a different reservation plan"
                )

            active = [
                item
                for item in self._records.values()
                if item.status == "held" and item.expires_at > current
            ]
            _assert_capacity_available(plan.reservations, active, supply)
            for item in plan.reservations:
                self._records[item.reservation_id] = item.model_copy(deep=True)
            return [item.model_copy(deep=True) for item in plan.reservations]

    def list_active(
        self, *, now: datetime | None = None
    ) -> list[EventCapacityReservation]:
        current = now or datetime.now(UTC)
        if self._db:
            return self._db.list_active(now=current)
        with self._lock:
            self._expire_locked(current)
            return [
                item.model_copy(deep=True)
                for item in self._records.values()
                if item.status == "held" and item.expires_at > current
            ]

    def release(self, event_id: str, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        if self._db:
            return self._db.release(event_id, now=current)
        with self._lock:
            released = 0
            for key, item in list(self._records.items()):
                if item.event_id == event_id and item.status == "held":
                    self._records[key] = item.model_copy(
                        update={"status": "released", "released_at": current}
                    )
                    released += 1
            return released

    def _expire_locked(self, current: datetime) -> None:
        for key, item in list(self._records.items()):
            if item.status == "held" and item.expires_at <= current:
                self._records[key] = item.model_copy(update={"status": "expired"})


def _require_supply_identity(
    plan: EventReservationPlan, supply: EventCapacitySupply
) -> None:
    if (
        plan.matrix_id != supply.matrix_id
        or plan.matrix_digest != supply.matrix_digest
        or plan.fleet_snapshot_id != supply.fleet_snapshot_id
    ):
        raise EventReservationConflictError(
            "Reservation plan does not match current capacity evidence"
        )


def _reservation_payload(records: list[EventCapacityReservation]) -> list[dict]:
    fields = {
        "reservation_id",
        "event_id",
        "cohort_id",
        "lab_ref",
        "catalog_id",
        "catalog_release",
        "cluster_ref",
        "matrix_id",
        "matrix_digest",
        "fleet_snapshot_id",
        "resources",
        "expires_at",
    }
    return sorted(
        [item.model_dump(mode="json", include=fields) for item in records],
        key=lambda item: item["reservation_id"],
    )


def _assert_capacity_available(
    requested: list[EventCapacityReservation],
    active: list[EventCapacityReservation],
    supply: EventCapacitySupply,
) -> None:
    clusters = {item.cluster_id: item for item in supply.clusters}
    for item in requested:
        cluster = clusters.get(item.cluster_ref)
        if cluster is None or not cluster.enabled:
            raise EventReservationUnavailableError(
                f"Cluster {item.cluster_ref} is not eligible for reservation"
            )
        catalog = next(
            (
                entry
                for entry in cluster.catalogs
                if entry.catalog_id == item.catalog_id
                and entry.catalog_release == item.catalog_release
            ),
            None,
        )
        if catalog is None:
            raise EventReservationConflictError(
                "Reservation catalog release is not certified on its target cluster"
            )
        expected = catalog.resources_per_seat.scaled(item.resources.seats)
        expected.seats = item.resources.seats
        if expected != item.resources:
            raise EventReservationConflictError(
                "Reservation resources do not match the certified catalog footprint"
            )

    all_holds = active + requested
    for cluster_ref in sorted({item.cluster_ref for item in requested}):
        cluster = clusters.get(cluster_ref)
        if cluster is None or not cluster.enabled:
            raise EventReservationUnavailableError(
                f"Cluster {cluster_ref} is not eligible for reservation"
            )
        cluster_holds = [item for item in all_holds if item.cluster_ref == cluster_ref]
        demand = EventResourceVector()
        for item in cluster_holds:
            demand = demand.plus(item.resources)
        capacity = cluster.resource_capacity.model_copy(
            update={"seats": cluster.certified_seats}
        )
        exceeded = demand.exceeds(capacity)
        if exceeded:
            raise EventReservationUnavailableError(
                f"Cluster {cluster_ref} lacks certified remaining "
                f"{', '.join(exceeded)} capacity"
            )

        for catalog in cluster.catalogs:
            held_seats = sum(
                item.resources.seats
                for item in cluster_holds
                if item.catalog_id == catalog.catalog_id
                and item.catalog_release == catalog.catalog_release
            )
            if held_seats > catalog.certified_seats:
                raise EventReservationUnavailableError(
                    f"Cluster {cluster_ref} catalog {catalog.catalog_id}@"
                    f"{catalog.catalog_release} lacks certified remaining seats"
                )
