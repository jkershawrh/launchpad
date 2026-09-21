"""Atomic event-capacity reservations with no provisioning side effects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from app.domain.event_model_health import EventModelHealthSnapshot
from app.domain.events import (
    EventAdmissionForecast,
    EventCapacityReservation,
    EventCapacitySupply,
    EventClusterAdmissionForecast,
    EventRecord,
    EventReservationConsumption,
    EventReservationPlan,
    EventResourceVector,
)
from app.services.event_model_health import assess_event_model_health


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
    model_health: EventModelHealthSnapshot | None = None,
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
    labs = {item.lab_ref: item for item in record.manifest.labs}
    reservations: list[EventCapacityReservation] = []
    for allocation in preview.allocations:
        cluster = clusters.get(allocation.cluster_id)
        if cluster is None or not cluster.enabled:
            raise EventReservationConflictError(
                f"Allocated cluster {allocation.cluster_id} is no longer eligible"
            )
        lab = labs[allocation.lab_ref]
        if not set(lab.required_models).issubset(cluster.certified_models):
            raise EventReservationConflictError(
                f"Allocated cluster {allocation.cluster_id} lacks exact required model certification"
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
        if not set(catalog.required_models).issubset(lab.required_models):
            raise EventReservationConflictError(
                "Approved event omitted a required model from the certified catalog release"
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
    health = assess_event_model_health(record, model_health, current)
    if health.status == "blocked":
        raise EventReservationConflictError(health.explanation)
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
                if item.status in {"held", "consumed", "expired"}
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
                if item.status in {"held", "consumed", "expired"}
            ]

    def snapshot_active(self) -> list[EventCapacityReservation]:
        """Return capacity-bearing reservations without lifecycle mutation."""

        if self._db:
            return self._db.list_active(now=datetime.now(UTC))
        with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._records.values()
                if item.status in {"held", "consumed", "expired"}
            ]

    def list_for_event(
        self,
        event_id: str,
        *,
        now: datetime | None = None,
    ) -> list[EventCapacityReservation]:
        current = now or datetime.now(UTC)
        if self._db:
            return self._db.list_for_event(event_id, now=current)
        with self._lock:
            self._expire_locked(current)
            return sorted(
                [
                    item.model_copy(deep=True)
                    for item in self._records.values()
                    if item.event_id == event_id
                ],
                key=lambda item: (item.cohort_id, item.lab_ref, item.reservation_id),
            )

    def get(
        self,
        reservation_id: str,
        *,
        now: datetime | None = None,
    ) -> EventCapacityReservation | None:
        current = now or datetime.now(UTC)
        if self._db:
            return self._db.get(reservation_id, now=current)
        with self._lock:
            self._expire_locked(current)
            reservation = self._records.get(reservation_id)
            return reservation.model_copy(deep=True) if reservation else None

    def consume(
        self,
        binding: EventReservationConsumption,
        *,
        now: datetime | None = None,
    ) -> EventCapacityReservation:
        current = now or datetime.now(UTC)
        if self._db:
            return self._db.consume(binding, now=current)
        with self._lock:
            self._expire_locked(current)
            reservation = self._records.get(binding.reservation_id)
            if reservation is None:
                raise EventReservationConflictError("Reservation was not found")
            if any(
                item.reservation_id != binding.reservation_id
                and item.workshop_id == binding.workshop_id
                for item in self._records.values()
            ):
                raise EventReservationConflictError(
                    "Workshop is bound to a different reservation"
                )
            _assert_consumption_matches(reservation, binding)
            if reservation.status == "consumed":
                if reservation.workshop_id != binding.workshop_id:
                    raise EventReservationConflictError(
                        "Reservation is bound to a different workshop"
                    )
                return reservation.model_copy(deep=True)
            if reservation.status == "expired":
                raise EventReservationConflictError(
                    "Reservation expired before workshop consumption"
                )
            if reservation.status == "released":
                raise EventReservationConflictError(
                    "Released reservation cannot be consumed"
                )
            consumed = reservation.model_copy(
                update={
                    "status": "consumed",
                    "consumed_at": current,
                    "workshop_id": binding.workshop_id,
                }
            )
            self._records[reservation.reservation_id] = consumed
            return consumed.model_copy(deep=True)

    def release(
        self,
        event_id: str,
        *,
        cleanup_evidence_id: str,
        now: datetime | None = None,
    ) -> int:
        if not cleanup_evidence_id.strip():
            raise EventReservationConflictError("Cleanup evidence is required")
        current = now or datetime.now(UTC)
        if self._db:
            return self._db.release(
                event_id,
                cleanup_evidence_id=cleanup_evidence_id,
                now=current,
            )
        with self._lock:
            released = 0
            for key, item in list(self._records.items()):
                if (
                    item.event_id == event_id
                    and item.status == "released"
                    and item.cleanup_evidence_id != cleanup_evidence_id
                ):
                    raise EventReservationConflictError(
                        "Event was released with different cleanup evidence"
                    )
                if item.event_id == event_id and item.status in {
                    "held",
                    "consumed",
                    "expired",
                }:
                    self._records[key] = item.model_copy(
                        update={
                            "status": "released",
                            "released_at": current,
                            "cleanup_evidence_id": cleanup_evidence_id,
                        }
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


def _assert_consumption_matches(
    reservation: EventCapacityReservation,
    binding: EventReservationConsumption,
) -> None:
    expected = {
        "reservation_id": reservation.reservation_id,
        "event_id": reservation.event_id,
        "cluster_ref": reservation.cluster_ref,
        "catalog_id": reservation.catalog_id,
        "catalog_release": reservation.catalog_release,
        "seats": reservation.resources.seats,
    }
    supplied = binding.model_dump(exclude={"workshop_id"})
    if supplied != expected:
        raise EventReservationConflictError(
            "Workshop consumption does not match the reserved event allocation"
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


def forecast_event_admission(
    record: EventRecord,
    supply: EventCapacitySupply,
    active: list[EventCapacityReservation],
    *,
    now: datetime | None = None,
    model_health: EventModelHealthSnapshot | None = None,
) -> EventAdmissionForecast:
    """Forecast admission against current evidence without creating a hold."""

    current = now or datetime.now(UTC)
    health = assess_event_model_health(record, model_health, current)
    preview = record.capacity_preview
    evidence_matches = (
        preview.matrix_id,
        preview.matrix_digest,
        preview.fleet_snapshot_id,
    ) == (
        supply.matrix_id,
        supply.matrix_digest,
        supply.fleet_snapshot_id,
    )
    existing = [item for item in active if item.event_id == record.manifest.event_id]
    active_other = [item for item in active if item.event_id != record.manifest.event_id]

    if existing:
        expired = any(
            item.status == "expired"
            or (item.status == "held" and item.expires_at <= current)
            for item in existing
        )
        clusters = _build_cluster_forecasts(record, supply, existing, active_other)
        expected = {
            (item.cohort_id, item.lab_ref) for item in preview.allocations
        }
        held = {(item.cohort_id, item.lab_ref) for item in existing}
        fresh = _fleet_snapshot_fresh(supply, current)
        eligible = (
            evidence_matches
            and fresh
            and health.status != "blocked"
            and not expired
            and held == expected
            and all(item.eligible for item in clusters)
        )
        return EventAdmissionForecast(
            event_id=record.manifest.event_id,
            status="reserved" if eligible else "blocked",
            eligible=eligible,
            evidence_matches=evidence_matches,
            current_active_reservations=len(active),
            matrix_id=supply.matrix_id,
            matrix_digest=supply.matrix_digest,
            fleet_snapshot_id=supply.fleet_snapshot_id,
            model_health_status=health.status,
            model_health_snapshot_id=health.snapshot_id,
            clusters=clusters,
            explanation=(
                "Capacity is already reserved and placement remains pinned."
                if eligible
                else health.explanation if health.status == "blocked"
                else "The existing event reservation has incomplete, expired, stale, or drifted certification evidence."
            ),
            observed_at=current,
        )

    try:
        plan = build_event_reservation_plan(
            record,
            supply,
            expires_at=current + timedelta(minutes=5),
            now=current,
            model_health=model_health,
        )
    except (EventReservationConflictError, EventReservationUnavailableError) as exc:
        return EventAdmissionForecast(
            event_id=record.manifest.event_id,
            status="blocked",
            eligible=False,
            evidence_matches=evidence_matches,
            current_active_reservations=len(active),
            matrix_id=supply.matrix_id,
            matrix_digest=supply.matrix_digest,
            fleet_snapshot_id=supply.fleet_snapshot_id,
            model_health_status=health.status,
            model_health_snapshot_id=health.snapshot_id,
            explanation=str(exc),
            observed_at=current,
        )

    clusters = _build_cluster_forecasts(
        record, supply, plan.reservations, active_other
    )
    eligible = all(item.eligible for item in clusters)
    return EventAdmissionForecast(
        event_id=record.manifest.event_id,
        status="available" if eligible else "blocked",
        eligible=eligible,
        evidence_matches=evidence_matches,
        current_active_reservations=len(active),
        matrix_id=supply.matrix_id,
        matrix_digest=supply.matrix_digest,
        fleet_snapshot_id=supply.fleet_snapshot_id,
        model_health_status=health.status,
        model_health_snapshot_id=health.snapshot_id,
        clusters=clusters,
        explanation=(
            "Current certified capacity can satisfy the complete event reservation."
            if eligible
            else "Current reservations leave insufficient certified capacity."
        ),
        observed_at=current,
    )


def _build_cluster_forecasts(
    record: EventRecord,
    supply: EventCapacitySupply,
    requested: list[EventCapacityReservation],
    active_other: list[EventCapacityReservation],
) -> list[EventClusterAdmissionForecast]:
    clusters = {item.cluster_id: item for item in supply.clusters}
    labs = {item.lab_ref: item for item in record.manifest.labs}
    results: list[EventClusterAdmissionForecast] = []
    for cluster_id in sorted({item.cluster_ref for item in requested}):
        cluster = clusters.get(cluster_id)
        cluster_requested = [item for item in requested if item.cluster_ref == cluster_id]
        cluster_reserved = [item for item in active_other if item.cluster_ref == cluster_id]
        demand = _sum_resources(cluster_requested)
        reserved = _sum_resources(cluster_reserved)
        if cluster is None or not cluster.enabled:
            zero = EventResourceVector()
            results.append(
                EventClusterAdmissionForecast(
                    cluster_id=cluster_id,
                    demand=demand,
                    reserved=reserved,
                    certified=zero,
                    remaining_after_event=zero,
                    eligible=False,
                    blockers=["cluster_ineligible"],
                )
            )
            continue
        certified = cluster.resource_capacity.model_copy(
            update={"seats": cluster.certified_seats}
        )
        total = reserved.plus(demand)
        blockers = total.exceeds(certified)
        if record.manifest.exposure_policy not in cluster.exposure_policies:
            blockers.append("exposure_policy")
        if any(
            (item.matrix_id, item.matrix_digest, item.fleet_snapshot_id)
            != (supply.matrix_id, supply.matrix_digest, supply.fleet_snapshot_id)
            for item in cluster_requested
        ):
            blockers.append("capacity_evidence_drift")
        for item in cluster_requested:
            lab = labs[item.lab_ref]
            blockers.extend(
                capability
                for capability in lab.required_capabilities
                if capability not in cluster.capabilities
            )
            blockers.extend(
                f"model:{model_id}"
                for model_id in lab.required_models
                if model_id not in cluster.certified_models
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
                blockers.append(f"catalog:{item.catalog_id}@{item.catalog_release}")
            else:
                if not set(catalog.required_models).issubset(lab.required_models):
                    blockers.append(f"catalog-models:{item.catalog_id}@{item.catalog_release}")
                expected = catalog.resources_per_seat.scaled(item.resources.seats)
                expected.seats = item.resources.seats
                if expected != item.resources:
                    blockers.append(f"footprint:{item.catalog_id}@{item.catalog_release}")
        for catalog in cluster.catalogs:
            held = sum(
                item.resources.seats
                for item in cluster_reserved + cluster_requested
                if item.catalog_id == catalog.catalog_id
                and item.catalog_release == catalog.catalog_release
            )
            if held > catalog.certified_seats:
                blockers.append(f"catalog:{catalog.catalog_id}@{catalog.catalog_release}")
        remaining = EventResourceVector(
            **{
                key: max(0, value - total.model_dump()[key])
                for key, value in certified.model_dump().items()
            }
        )
        lab_refs = {item.lab_ref for item in cluster_requested}
        results.append(
            EventClusterAdmissionForecast(
                cluster_id=cluster_id,
                demand=demand,
                reserved=reserved,
                certified=certified,
                remaining_after_event=remaining,
                required_capabilities=sorted(
                    {
                        capability
                        for lab_ref in lab_refs
                        for capability in labs[lab_ref].required_capabilities
                    }
                ),
                catalog_releases=sorted(
                    {f"{item.catalog_id}@{item.catalog_release}" for item in cluster_requested}
                ),
                eligible=not blockers,
                blockers=sorted(set(blockers)),
            )
        )
    return results


def _sum_resources(
    reservations: list[EventCapacityReservation],
) -> EventResourceVector:
    total = EventResourceVector()
    for item in reservations:
        total = total.plus(item.resources)
    return total


def _fleet_snapshot_fresh(supply: EventCapacitySupply, current: datetime) -> bool:
    observed = supply.fleet_observed_at
    if observed is None or observed.tzinfo is None or supply.fleet_snapshot_id == "not-evaluated":
        return False
    return -30 <= (current - observed).total_seconds() <= 120
