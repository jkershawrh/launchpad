"""Local-only boundary for *complete* physical capacity accounting evidence.

No Kubernetes adapter is included. A future read-only adapter must list all
namespaces and pods, node allocatable, and model slots from the selected
server-owned target, then attest each inventory dimension. A partial scan is
never serialized as an admission-ready snapshot.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.domain.clusters import ClusterTarget
from app.domain.events import EventCapacityReservation
from app.services.event_inflight_capacity_provider import (
    FileEventInflightCapacityProvider,
)

_PREFIX = "launchpad.redhat.com/"
_RESERVATION = _PREFIX + "event-reservation-id"
_WORKSHOP = _PREFIX + "workshop-id"
_SEAT = _PREFIX + "seat-id"


class InflightCollectionBlocked(RuntimeError):
    """A complete, trustworthy snapshot cannot be established."""


@dataclass(frozen=True)
class PodRequest:
    """Effective request of one pod, including init max and pod overhead."""

    uid: str
    cpu_millicores: int
    memory_mib: int
    model_slots: int = 0


@dataclass(frozen=True)
class NamespaceInventory:
    name: str
    labels: dict[str, str]
    pods: tuple[PodRequest, ...] = ()


@dataclass(frozen=True)
class ClusterInventory:
    cluster_id: str
    observed_at: datetime
    allocatable_cpu_millicores: int
    allocatable_memory_mib: int
    allocatable_pods: int
    allocatable_model_slots: int
    # Independent namespace roster detects omission from per-namespace scans.
    namespace_names: tuple[str, ...]
    namespaces: tuple[NamespaceInventory, ...]
    node_inventory_complete: bool = False
    namespace_inventory_complete: bool = False
    pod_inventory_complete: bool = False
    request_inventory_complete: bool = False
    model_slot_inventory_complete: bool = False


class ClusterInventoryObserver(Protocol):
    def observe(self, target: ClusterTarget) -> ClusterInventory:
        """Read only from this target; never fall back to another cluster."""


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise InflightCollectionBlocked(f"incomplete {name} identity")
    return value


def _nonnegative(value: int, name: str) -> int:
    if type(value) is not int or value < 0:
        raise InflightCollectionBlocked(f"incomplete {name} accounting")
    return value


def _reservation_index(
    reservations: list[EventCapacityReservation], targets: set[str]
) -> tuple[dict[str, EventCapacityReservation], dict[tuple[str, str], str]]:
    by_id: dict[str, EventCapacityReservation] = {}
    by_workshop: dict[tuple[str, str], str] = {}
    for reservation in reservations:
        if reservation.status not in {"held", "consumed", "expired"}:
            raise InflightCollectionBlocked("inactive reservation in active accounting")
        if reservation.cluster_ref not in targets:
            raise InflightCollectionBlocked("reservation cluster is outside explicit targets")
        if reservation.reservation_id in by_id:
            raise InflightCollectionBlocked("duplicate reservation identity")
        by_id[reservation.reservation_id] = reservation
        if reservation.workshop_id:
            key = (reservation.cluster_ref, reservation.workshop_id)
            if key in by_workshop:
                raise InflightCollectionBlocked("duplicate workshop reservation identity")
            by_workshop[key] = reservation.reservation_id
    return by_id, by_workshop


def collect_inflight_capacity(
    targets: list[ClusterTarget],
    active_reservations: list[EventCapacityReservation],
    observer: ClusterInventoryObserver,
    *,
    now: datetime,
    persisted_seats: dict[str, set[str]],
) -> dict:
    """Build provider-compatible evidence only from complete, exact inventories.

    The caller must obtain reservation state from the authoritative ledger in
    the same collection window. This is evidence, not an atomic admission lock.
    """

    if now.tzinfo is None:
        raise InflightCollectionBlocked("observation time requires a timezone")
    ids = [_identity(target.cluster_id, "cluster") for target in targets]
    if not ids or len(ids) != len(set(ids)):
        raise InflightCollectionBlocked("explicit cluster targets are missing or duplicated")
    by_id, by_workshop = _reservation_index(active_reservations, set(ids))
    for reservation in active_reservations:
        if reservation.status != "consumed":
            continue
        seats = persisted_seats.get(reservation.workshop_id or "")
        if (
            seats is None
            or len(seats) != reservation.resources.seats
            or any(not isinstance(seat, str) or not seat.strip() for seat in seats)
        ):
            raise InflightCollectionBlocked("persisted workshop seat identity is incomplete")
    clusters: list[dict] = []
    seen_seats: set[tuple[str, str]] = set()
    for target in targets:
        if not target.enabled:
            raise InflightCollectionBlocked("disabled cluster cannot produce capacity evidence")
        try:
            inventory = observer.observe(target)
        except Exception as exc:
            raise InflightCollectionBlocked("cluster inventory unavailable") from exc
        if not isinstance(inventory, ClusterInventory) or inventory.cluster_id != target.cluster_id:
            raise InflightCollectionBlocked("cluster inventory identity mismatch")
        if inventory.observed_at.tzinfo is None:
            raise InflightCollectionBlocked("cluster observation time requires a timezone")
        age = (now - inventory.observed_at).total_seconds()
        if age > 120 or age < -30:
            raise InflightCollectionBlocked("cluster inventory is stale or future-dated")
        if not all(
            (
                inventory.node_inventory_complete,
                inventory.namespace_inventory_complete,
                inventory.pod_inventory_complete,
                inventory.request_inventory_complete,
                inventory.model_slot_inventory_complete,
            )
        ):
            raise InflightCollectionBlocked("cluster inventory incomplete")
        allocatable = {
            "cpu_millicores": _nonnegative(inventory.allocatable_cpu_millicores, "CPU"),
            "memory_mib": _nonnegative(inventory.allocatable_memory_mib, "memory"),
            "pods": _nonnegative(inventory.allocatable_pods, "pod slots"),
            "model_slots": _nonnegative(inventory.allocatable_model_slots, "model slots"),
        }
        roster = tuple(_identity(name, "namespace") for name in inventory.namespace_names)
        names = tuple(_identity(row.name, "namespace") for row in inventory.namespaces)
        if (
            len(roster) != len(set(roster))
            or len(names) != len(set(names))
            or set(roster) != set(names)
        ):
            raise InflightCollectionBlocked("namespace roster is incomplete or duplicated")
        seen_pods: set[str] = set()
        workloads: list[dict] = []
        for row in sorted(inventory.namespaces, key=lambda item: item.name):
            if not isinstance(row.labels, dict):
                raise InflightCollectionBlocked("namespace identity labels are incomplete")
            labels = row.labels
            reservation_id = labels.get(_RESERVATION)
            workshop_id = labels.get(_WORKSHOP)
            seat_id = labels.get(_SEAT)
            for label, value in (
                ("reservation", reservation_id),
                ("workshop", workshop_id),
                ("seat", seat_id),
            ):
                if value is not None:
                    _identity(value, f"{label} label")
            expected = by_workshop.get((target.cluster_id, workshop_id or ""))
            if workshop_id and expected is None and reservation_id:
                raise InflightCollectionBlocked("event namespace identity is incomplete")
            # Ordinary workshops also carry workshop-id and seat-id. Their pods
            # remain physical usage but do not consume an event reservation.
            if expected and (reservation_id != expected or not seat_id):
                raise InflightCollectionBlocked("event namespace identity is incomplete")
            if reservation_id or (seat_id and not workshop_id):
                if not (reservation_id and workshop_id and seat_id):
                    raise InflightCollectionBlocked("event namespace identity is incomplete")
                reservation = by_id.get(reservation_id)
                if reservation is None:
                    raise InflightCollectionBlocked("unknown event reservation identity")
                if reservation.cluster_ref != target.cluster_id:
                    raise InflightCollectionBlocked("reservation cluster identity mismatch")
                if reservation.status != "consumed" or reservation.workshop_id != workshop_id:
                    raise InflightCollectionBlocked("reservation workshop identity mismatch")
                key = (reservation_id, seat_id)
                if seat_id not in persisted_seats[workshop_id]:
                    raise InflightCollectionBlocked("seat is absent from persisted workshop")
                if key in seen_seats:
                    raise InflightCollectionBlocked("duplicate reservation seat identity")
                seen_seats.add(key)
                _identity(seat_id, "seat")
            resources = {"cpu_millicores": 0, "memory_mib": 0, "pods": 0, "model_slots": 0}
            for pod in row.pods:
                uid = _identity(pod.uid, "pod")
                if uid in seen_pods:
                    raise InflightCollectionBlocked("duplicate pod identity")
                seen_pods.add(uid)
                resources["cpu_millicores"] += _nonnegative(pod.cpu_millicores, "pod CPU")
                resources["memory_mib"] += _nonnegative(pod.memory_mib, "pod memory")
                resources["model_slots"] += _nonnegative(pod.model_slots, "pod model slots")
                resources["pods"] += 1
            workloads.append(
                {
                    "namespace": row.name,
                    "reservation_id": reservation_id,
                    "workshop_id": workshop_id if reservation_id else None,
                    "seat_refs": [seat_id] if reservation_id else [],
                    "resources": resources,
                }
            )
        clusters.append(
            {
                "cluster_id": target.cluster_id,
                "allocatable": allocatable,
                "accounting_complete": True,
                "workloads": workloads,
            }
        )
    return {"schema_version": "1.0", "observed_at": now.isoformat(), "clusters": clusters}


def write_inflight_capacity_snapshot(path: str | Path, document: dict) -> None:
    """Validate then atomically replace a private evidence file, never partial."""

    destination = Path(path)
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".inflight-", dir=destination.parent)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Provider verifies strict schema and derives the byte digest.
        FileEventInflightCapacityProvider(temporary).load()
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
