"""Pure fail-closed reconciliation of runtime usage and active event holds."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.event_inflight_capacity import (
    EventInflightCapacitySnapshot,
    InflightResourceVector,
)
from app.domain.events import EventCapacityReservation

DIMENSIONS = ("cpu_millicores", "memory_mib", "pods", "model_slots")


@dataclass(frozen=True)
class InflightCapacityAssessment:
    status: str
    explanation: str
    snapshot_id: str | None = None
    headroom: dict[str, InflightResourceVector] = field(default_factory=dict)


def _blocked(reason: str, snapshot_id: str | None = None, *, headroom=None):
    return InflightCapacityAssessment("blocked", reason, snapshot_id, headroom or {})


def _values(vector) -> dict[str, int]:
    return {dimension: getattr(vector, dimension) for dimension in DIMENSIONS}


def assess_event_inflight_capacity(
    candidate: dict[str, InflightResourceVector],
    active: list[EventCapacityReservation],
    snapshot: EventInflightCapacitySnapshot | None,
    *,
    now: datetime,
) -> InflightCapacityAssessment:
    """Bound candidate demand by observed free capacity, including unused holds.

    Physical free already excludes observed reservation and external workloads.
    Only the *unobserved remainder* of each active reservation is subtracted,
    preventing consumed holds from being counted twice. The caller must still
    run the certified matrix and ledger gates atomically; this is a separate
    read-only safety bound, never a replacement for either.
    """

    if not candidate:
        return InflightCapacityAssessment("not_required", "No in-flight capacity requested")
    if snapshot is None:
        return _blocked("In-flight capacity evidence is unavailable")
    if now.tzinfo is None:
        return _blocked("Admission time requires a timezone", snapshot.snapshot_id)
    age = (now - snapshot.observed_at).total_seconds()
    if age > 120:
        return _blocked("In-flight capacity evidence is stale", snapshot.snapshot_id)
    if age < -30:
        return _blocked("In-flight capacity evidence is future-dated", snapshot.snapshot_id)

    reservations = {item.reservation_id: item for item in active}
    if len(reservations) != len(active):
        return _blocked("Duplicate active reservation identity", snapshot.snapshot_id)
    if any(item.status not in {"held", "consumed", "expired"} for item in active):
        return _blocked("Inactive reservation supplied as capacity-bearing", snapshot.snapshot_id)

    observed_clusters = {item.cluster_id: item for item in snapshot.clusters}
    headroom: dict[str, InflightResourceVector] = {}
    for cluster_id, demand in sorted(candidate.items()):
        cluster = observed_clusters.get(cluster_id)
        if cluster is None:
            return _blocked(
                f"In-flight capacity evidence missing cluster {cluster_id}", snapshot.snapshot_id
            )
        if not cluster.accounting_complete:
            return _blocked(
                f"In-flight capacity accounting incomplete on {cluster_id}", snapshot.snapshot_id
            )

        observed_total = {dimension: 0 for dimension in DIMENSIONS}
        observed_by_reservation: dict[str, dict[str, int]] = {}
        seats_by_reservation: dict[str, set[str]] = {}
        namespace_owners: dict[str, str | None] = {}
        for workload in cluster.workloads:
            owner = workload.reservation_id
            prior_owner = namespace_owners.get(workload.namespace)
            if workload.namespace in namespace_owners and prior_owner != owner:
                return _blocked(
                    f"In-flight capacity ambiguous namespace {workload.namespace} on {cluster_id}",
                    snapshot.snapshot_id,
                )
            namespace_owners[workload.namespace] = owner
            for dimension, amount in _values(workload.resources).items():
                observed_total[dimension] += amount
            if owner is None:
                continue
            reservation = reservations.get(owner)
            if reservation is None:
                return _blocked(
                    f"In-flight workload has unknown reservation {owner}", snapshot.snapshot_id
                )
            if reservation.cluster_ref != cluster_id:
                return _blocked(
                    f"Reservation {owner} belongs to another cluster", snapshot.snapshot_id
                )
            if reservation.status != "consumed" or reservation.workshop_id != workload.workshop_id:
                return _blocked(
                    f"In-flight workload workshop/state mismatch for {owner}", snapshot.snapshot_id
                )
            seen_seats = seats_by_reservation.setdefault(owner, set())
            if len(workload.seat_refs) != len(set(workload.seat_refs)) or any(
                seat in seen_seats for seat in workload.seat_refs
            ):
                return _blocked(
                    f"In-flight workload has duplicate seat for {owner}", snapshot.snapshot_id
                )
            seen_seats.update(workload.seat_refs)
            if len(seen_seats) > reservation.resources.seats:
                return _blocked(
                    f"In-flight workload exceeds seat limit for {owner}", snapshot.snapshot_id
                )
            owned = observed_by_reservation.setdefault(
                owner, {dimension: 0 for dimension in DIMENSIONS}
            )
            for dimension, amount in _values(workload.resources).items():
                owned[dimension] += amount

        free = {
            dimension: getattr(cluster.allocatable, dimension) - observed_total[dimension]
            for dimension in DIMENSIONS
        }
        if any(value < 0 for value in free.values()):
            return _blocked(
                f"Observed usage exceeds allocatable on {cluster_id}", snapshot.snapshot_id
            )
        for reservation in active:
            if reservation.cluster_ref != cluster_id:
                continue
            owned = observed_by_reservation.get(
                reservation.reservation_id,
                {dimension: 0 for dimension in DIMENSIONS},
            )
            for dimension in DIMENSIONS:
                reserved = getattr(reservation.resources, dimension)
                if owned[dimension] > reserved:
                    return _blocked(
                        f"Observed usage exceeds reservation {reservation.reservation_id}",
                        snapshot.snapshot_id,
                    )
                free[dimension] -= reserved - owned[dimension]
        if any(value < 0 for value in free.values()):
            return _blocked(
                f"Active holds exceed observed free capacity on {cluster_id}",
                snapshot.snapshot_id,
            )
        headroom[cluster_id] = InflightResourceVector(**free)
        exceeded = [
            dimension for dimension, amount in _values(demand).items() if amount > free[dimension]
        ]
        if exceeded:
            return _blocked(
                f"In-flight capacity exhausted on {cluster_id}: {', '.join(exceeded)}",
                snapshot.snapshot_id,
                headroom=headroom,
            )
    return InflightCapacityAssessment(
        "available",
        "Observed physical headroom covers candidate demand",
        snapshot.snapshot_id,
        headroom,
    )
