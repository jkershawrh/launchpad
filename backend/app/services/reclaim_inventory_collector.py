"""Normalize injected, read-only roster observations for reclaim-readiness/v1.

There is deliberately no Kubernetes, database, or HTTP client here. Providers
must be independently implemented and reviewed; their completeness assertions
are an external trust boundary, not proof supplied by this module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.services.reclaim_readiness import evaluate_reclaim_readiness


class InventoryCollectionError(ValueError):
    """An incomplete or inconsistent observation; do not proceed to reclaim."""


@dataclass(frozen=True)
class CollectionBatch:
    rows: list[Mapping[str, Any]]
    complete: bool
    observed_at: datetime


class ReclaimInventorySource(Protocol):
    """Injected read-only provider of complete, scoped observations."""

    def list_cluster_refs(self) -> CollectionBatch: ...

    def list_retained_workshops(self) -> CollectionBatch: ...

    def list_sessions(self, workshop_ids: frozenset[str]) -> CollectionBatch: ...

    def list_reservations(self, workshop_ids: frozenset[str]) -> CollectionBatch: ...

    def list_managed_namespaces(self, cluster_ref: str) -> CollectionBatch: ...


_FIELDS = {
    "cluster": ("cluster_ref",),
    "workshop": ("workshop_id", "cluster_ref", "seat_count", "reservation_id", "state"),
    "session": ("session_id", "workshop_id", "cluster_ref", "namespace", "seat_number", "state"),
    "reservation": ("reservation_id", "workshop_id", "cluster_ref", "seat_count", "state"),
    "namespace": ("namespace", "cluster_ref", "workshop_id", "session_id"),
}
_LIMITS = {"cluster": 100, "workshop": 100, "session": 5000, "reservation": 100, "namespace": 5000}


def _checked_batch(
    batch: CollectionBatch,
    kind: str,
    *,
    now: datetime,
    max_age: timedelta,
) -> tuple[list[dict[str, Any]], datetime]:
    if not isinstance(batch, CollectionBatch) or batch.complete is not True:
        raise InventoryCollectionError(f"{kind} observation is incomplete")
    observed_at = batch.observed_at
    if (
        not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise InventoryCollectionError(f"{kind} observation has no trusted timestamp")
    age = now - observed_at
    if age < timedelta(0) or age > max_age:
        raise InventoryCollectionError(f"{kind} observation is stale or future-dated")
    if not isinstance(batch.rows, list) or len(batch.rows) > _LIMITS[kind]:
        raise InventoryCollectionError(f"{kind} observation exceeds its row limit")
    fields = _FIELDS[kind]
    rows: list[dict[str, Any]] = []
    for item in batch.rows:
        if not isinstance(item, Mapping) or any(field not in item for field in fields):
            raise InventoryCollectionError(f"{kind} observation has an invalid row")
        # Strict projection prevents provider metadata, emails and credentials
        # from entering the normalized inventory or diagnostic output.
        projected = {field: item[field] for field in fields}
        for field in ("cluster_ref", "workshop_id", "session_id", "namespace"):
            if field in projected and not isinstance(projected[field], str):
                raise InventoryCollectionError(f"{kind} observation has an invalid identifier")
        if "state" in projected and not isinstance(projected["state"], str):
            raise InventoryCollectionError(f"{kind} observation has an invalid state")
        if (
            "reservation_id" in projected
            and projected["reservation_id"] is not None
            and not isinstance(projected["reservation_id"], str)
        ):
            raise InventoryCollectionError(f"{kind} observation has an invalid reservation ID")
        rows.append(projected)
    return rows, observed_at


def build_reclaim_inventory(
    source: ReclaimInventorySource,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(minutes=30),
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Build and balance a supplied snapshot; never authorize or execute reclaim.

    The workshop roster must be a complete scan of *all retained* workshops.
    Namespace observation must cover every registered execution cluster, not
    only clusters that the roster happens to mention. The caller must audit
    source completeness and consistency separately.
    """
    supplied_now = now is not None
    supplied_clock = clock is not None
    clock = clock or (lambda: datetime.now(UTC))
    now = now or clock()
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
        or not isinstance(max_age, timedelta)
        or max_age <= timedelta(0)
    ):
        raise InventoryCollectionError("invalid collection time or freshness window")
    observed_times: list[datetime] = []

    def read(kind: str, call: Any) -> list[dict[str, Any]]:
        try:
            rows, observed_at = _checked_batch(call(), kind, now=now, max_age=max_age)
        except InventoryCollectionError:
            raise
        except Exception:  # noqa: BLE001 - provider boundary must suppress secret-bearing failures
            # A provider exception could contain endpoint details or secrets.
            raise InventoryCollectionError(f"{kind} observation failed") from None
        observed_times.append(observed_at)
        return rows

    clusters = read("cluster", source.list_cluster_refs)
    cluster_refs = [row["cluster_ref"] for row in clusters]
    if not cluster_refs or len(cluster_refs) != len(set(cluster_refs)):
        raise InventoryCollectionError("cluster roster is empty or duplicate")
    workshops = read("workshop", source.list_retained_workshops)
    workshop_ids = frozenset(row["workshop_id"] for row in workshops)
    if not workshops:
        raise InventoryCollectionError("retained workshop roster is empty")
    if len(workshop_ids) != len(workshops):
        raise InventoryCollectionError("retained workshop roster has duplicates")
    sessions = read("session", lambda: source.list_sessions(workshop_ids))
    reservations = read("reservation", lambda: source.list_reservations(workshop_ids))
    session_ids = frozenset(row["session_id"] for row in sessions)
    namespaces: list[dict[str, Any]] = []
    for cluster_ref in cluster_refs:
        observed = read(
            "namespace", lambda cluster_ref=cluster_ref: source.list_managed_namespaces(cluster_ref)
        )
        for row in observed:
            if row["cluster_ref"] != cluster_ref:
                raise InventoryCollectionError("namespace observation targets wrong cluster")
            if row["workshop_id"] in workshop_ids or row["session_id"] in session_ids:
                namespaces.append(row)

    payload = {
        "schema_version": "reclaim-readiness/v1",
        "captured_at": min(observed_times).isoformat(),
        "scope": {
            "workshop_ids": sorted(workshop_ids),
            "cluster_refs": sorted(cluster_refs),
            "workshops_complete": True,
            "sessions_complete": True,
            "namespaces_complete": True,
            "reservations_complete": True,
        },
        "workshops": workshops,
        "sessions": sessions,
        "namespaces": namespaces,
        "reservations": reservations,
    }
    # Recheck at completion: a slow multi-cluster scan may have aged out while
    # providers were responding. Explicit test `now` is a frozen clock unless
    # the test also injects a clock to model elapsed time.
    completed_at = clock() if supplied_clock or not supplied_now else now
    if (
        not isinstance(completed_at, datetime)
        or completed_at.tzinfo is None
        or completed_at.utcoffset() is None
    ):
        raise InventoryCollectionError("completion clock is not timezone-aware")
    result = evaluate_reclaim_readiness(payload, now=completed_at, max_age=max_age)
    if not result.ready:
        raise InventoryCollectionError(result.reason)
    return payload
