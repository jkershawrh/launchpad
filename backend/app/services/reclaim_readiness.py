"""Pure, fail-closed balance check for a supplied pre-reclaim inventory.

This module does not obtain an inventory, authorize reclaim, or call a cluster.
It checks whether an independently captured inventory is internally complete
enough to enter the *separate* approved reclaim certification workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

_CLUSTER = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_MAX_WORKSHOPS = 100
_MAX_SEATS = 5000


@dataclass(frozen=True)
class ReclaimReadiness:
    ready: bool
    reason: str
    workshops: int = 0
    seats: int = 0


class _Blocked(ValueError):
    pass


def _object(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _Blocked(f"{name} must be an object")
    unexpected = set(value) - fields
    missing = fields - set(value)
    if unexpected:
        raise _Blocked(f"{name} has unexpected field: {min(unexpected)}")
    if missing:
        raise _Blocked(f"{name} is missing field: {min(missing)}")
    return value


def _list(value: Any, name: str, limit: int = _MAX_SEATS) -> list[Any]:
    if not isinstance(value, list) or len(value) > limit:
        raise _Blocked(f"{name} must be a list with at most {limit} entries")
    return value


def _uuid(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise _Blocked(f"{name} must be a full canonical UUID")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise _Blocked(f"{name} must be a full canonical UUID") from exc
    if str(parsed) != value:
        raise _Blocked(f"{name} must be a full canonical UUID")
    return value


def _slug(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _CLUSTER.fullmatch(value):
        raise _Blocked(f"{name} must be a DNS-safe name")
    return value


def _reservation_id(value: Any) -> str:
    # Event reservations use event:cohort:lab, not necessarily a UUID.
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or value.strip() != value
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise _Blocked("reservation_id must be a bounded opaque ID")
    return value


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value < 1 or value > _MAX_SEATS:
        raise _Blocked(f"{name} must be a positive bounded integer")
    return value


def _unique(values: list[str], name: str) -> None:
    if len(values) != len(set(values)):
        raise _Blocked(f"duplicate {name}")


def _evaluate(payload: Any, now: datetime, max_age: timedelta) -> ReclaimReadiness:
    if now.tzinfo is None or now.utcoffset() is None:
        raise _Blocked("now must be timezone-aware")
    root = _object(
        payload,
        {
            "schema_version",
            "captured_at",
            "scope",
            "workshops",
            "sessions",
            "namespaces",
            "reservations",
        },
        "inventory",
    )
    if root["schema_version"] != "reclaim-readiness/v1":
        raise _Blocked("unsupported inventory schema_version")
    try:
        captured_at = datetime.fromisoformat(root["captured_at"])
    except (TypeError, ValueError) as exc:
        raise _Blocked("captured_at must be ISO-8601") from exc
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise _Blocked("captured_at must be timezone-aware")
    age = now - captured_at
    if age < timedelta(0) or age > max_age:
        raise _Blocked("inventory is stale or future-dated")

    scope = _object(
        root["scope"],
        {
            "workshop_ids",
            "cluster_refs",
            "workshops_complete",
            "sessions_complete",
            "namespaces_complete",
            "reservations_complete",
        },
        "scope",
    )
    for field in (
        "workshops_complete",
        "sessions_complete",
        "namespaces_complete",
        "reservations_complete",
    ):
        if scope[field] is not True:
            raise _Blocked(f"incomplete inventory: {field}")
    expected_ids = [
        _uuid(item, "scope workshop_id")
        for item in _list(scope["workshop_ids"], "scope workshop_ids", _MAX_WORKSHOPS)
    ]
    _unique(expected_ids, "scope workshop_id")
    if not expected_ids:
        raise _Blocked("workshop scope cannot be empty")
    observed_clusters = [
        _slug(item, "scope cluster_ref")
        for item in _list(scope["cluster_refs"], "scope cluster_refs", _MAX_WORKSHOPS)
    ]
    _unique(observed_clusters, "scope cluster_ref")

    workshops: dict[str, dict[str, Any]] = {}
    for item in _list(root["workshops"], "workshops", _MAX_WORKSHOPS):
        row = _object(
            item,
            {"workshop_id", "cluster_ref", "seat_count", "reservation_id", "state"},
            "workshop",
        )
        workshop_id = _uuid(row["workshop_id"], "workshop_id")
        _slug(row["cluster_ref"], "workshop cluster_ref")
        _positive(row["seat_count"], "workshop seat_count")
        if row["reservation_id"] is not None:
            _reservation_id(row["reservation_id"])
        if row["state"] not in {"ready", "active"}:
            raise _Blocked("retained workshop must be ready or active")
        if workshop_id in workshops:
            raise _Blocked("duplicate workshop_id")
        workshops[workshop_id] = row
    if set(workshops) != set(expected_ids):
        raise _Blocked("workshop scope does not match workshop records")
    if not {row["cluster_ref"] for row in workshops.values()}.issubset(observed_clusters):
        raise _Blocked("cluster coverage does not include every persisted cluster_ref")

    sessions: dict[str, dict[str, Any]] = {}
    per_workshop: dict[str, set[int]] = {key: set() for key in workshops}
    namespace_keys: set[tuple[str, str]] = set()
    for item in _list(root["sessions"], "sessions"):
        row = _object(
            item,
            {"session_id", "workshop_id", "cluster_ref", "namespace", "seat_number", "state"},
            "session",
        )
        session_id = _uuid(row["session_id"], "session_id")
        workshop_id = _uuid(row["workshop_id"], "session workshop_id")
        cluster_ref = _slug(row["cluster_ref"], "session cluster_ref")
        namespace = _slug(row["namespace"], "session namespace")
        seat_number = _positive(row["seat_number"], "seat_number")
        if workshop_id not in workshops:
            raise _Blocked("session has unknown workshop ownership")
        if cluster_ref != workshops[workshop_id]["cluster_ref"]:
            raise _Blocked("session cluster_ref differs from persisted workshop cluster_ref")
        if row["state"] not in {"ready", "active"}:
            raise _Blocked("retained session must be ready or active")
        if session_id in sessions:
            raise _Blocked("duplicate session_id")
        key = (cluster_ref, namespace)
        if key in namespace_keys:
            raise _Blocked("duplicate session namespace")
        namespace_keys.add(key)
        sessions[session_id] = row
        if seat_number in per_workshop[workshop_id]:
            raise _Blocked("duplicate seat numbering")
        per_workshop[workshop_id].add(seat_number)
    for workshop_id, row in workshops.items():
        if len(per_workshop[workshop_id]) != row["seat_count"]:
            raise _Blocked("workshop seat count does not match sessions")
        if per_workshop[workshop_id] != set(range(1, row["seat_count"] + 1)):
            raise _Blocked("workshop seat numbering is not contiguous")

    namespaces: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _list(root["namespaces"], "namespaces"):
        row = _object(
            item,
            {"namespace", "cluster_ref", "workshop_id", "session_id"},
            "namespace",
        )
        key = (
            _slug(row["cluster_ref"], "namespace cluster_ref"),
            _slug(row["namespace"], "namespace name"),
        )
        _uuid(row["workshop_id"], "namespace workshop_id")
        _uuid(row["session_id"], "namespace session_id")
        if key in namespaces:
            raise _Blocked("duplicate namespace inventory record")
        namespaces[key] = row
    if set(namespaces) != namespace_keys:
        raise _Blocked("namespace inventory does not match session namespaces")
    for session_id, row in sessions.items():
        namespace = namespaces[(row["cluster_ref"], row["namespace"])]
        if namespace["session_id"] != session_id or namespace["workshop_id"] != row["workshop_id"]:
            raise _Blocked("namespace ownership differs from session")

    reservations: dict[str, dict[str, Any]] = {}
    for item in _list(root["reservations"], "reservations", _MAX_WORKSHOPS):
        row = _object(
            item,
            {"reservation_id", "workshop_id", "cluster_ref", "seat_count", "state"},
            "reservation",
        )
        reservation_id = _reservation_id(row["reservation_id"])
        _uuid(row["workshop_id"], "reservation workshop_id")
        _slug(row["cluster_ref"], "reservation cluster_ref")
        _positive(row["seat_count"], "reservation seat_count")
        if reservation_id in reservations:
            raise _Blocked("duplicate reservation_id")
        reservations[reservation_id] = row
    expected_reservations = {
        row["reservation_id"] for row in workshops.values() if row["reservation_id"] is not None
    }
    if set(reservations) != expected_reservations:
        raise _Blocked("reservation inventory does not match workshop reservations")
    for workshop_id, workshop in workshops.items():
        reservation_id = workshop["reservation_id"]
        if reservation_id is None:
            continue
        reservation = reservations[reservation_id]
        if (
            reservation["workshop_id"] != workshop_id
            or reservation["cluster_ref"] != workshop["cluster_ref"]
            or reservation["seat_count"] != workshop["seat_count"]
            or reservation["state"] != "consumed"
        ):
            raise _Blocked(
                "reservation ownership, cluster, seats, or state does not match workshop"
            )
    return ReclaimReadiness(True, "balanced", len(workshops), len(sessions))


def evaluate_reclaim_readiness(
    payload: Any,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(minutes=30),
) -> ReclaimReadiness:
    """Validate supplied inventory only; readiness is not reclaim authorization."""
    if max_age <= timedelta(0):
        return ReclaimReadiness(False, "max_age must be positive")
    try:
        return _evaluate(payload, now or datetime.now(UTC), max_age)
    except _Blocked as exc:
        return ReclaimReadiness(False, str(exc))


def main(argv: list[str] | None = None) -> int:
    """Read one local JSON input and print a non-secret validation result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="local JSON inventory to read")
    args = parser.parse_args(argv)
    try:
        if args.inventory.stat().st_size > 2_000_000:
            raise _Blocked("inventory exceeds the 2 MB read limit")
        payload = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = evaluate_reclaim_readiness(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, _Blocked):
        result = ReclaimReadiness(False, "inventory could not be read or parsed safely")
    print(
        json.dumps(
            {
                "ready": result.ready,
                "reason": result.reason,
                "workshops": result.workshops,
                "seats": result.seats,
            },
            sort_keys=True,
        )
    )
    return 0 if result.ready else 2


if __name__ == "__main__":
    sys.exit(main())
