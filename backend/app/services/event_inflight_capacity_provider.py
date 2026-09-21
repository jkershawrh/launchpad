"""Trusted, read-only file boundary for in-flight capacity accounting evidence.

The collector and its credential are deliberately separate. This provider cannot
assert that cluster accounting is complete; it only rejects malformed evidence
before the short-lived snapshot reaches the admission gate.
"""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.domain.event_inflight_capacity import EventInflightCapacitySnapshot

_RESOURCE_FIELDS = {"cpu_millicores", "memory_mib", "pods", "model_slots"}
_MAX_BYTES = 8 * 1024 * 1024


class EventInflightCapacityUnavailableError(RuntimeError):
    """Configured in-flight evidence cannot be read or trusted."""


def _object(value: Any, *, required: set[str], optional: set[str] = frozenset()) -> dict:
    if (
        type(value) is not dict
        or not required <= value.keys()
        or value.keys() - required - optional
    ):
        raise ValueError("invalid in-flight capacity object shape")
    return value


def _identifier(value: Any) -> None:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError("invalid in-flight capacity identifier")


def _resources(value: Any) -> None:
    fields = _object(value, required=_RESOURCE_FIELDS)
    if any(type(amount) is not int or amount < 0 for amount in fields.values()):
        raise ValueError("invalid in-flight resource amount")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in in-flight evidence")
        result[key] = value
    return result


def _validate_document(document: Any) -> dict:
    result = _object(document, required={"schema_version", "observed_at", "clusters"})
    if result["schema_version"] != "1.0":
        raise ValueError("unsupported in-flight capacity schema")
    observed_at = result["observed_at"]
    if type(observed_at) is not str:
        raise ValueError("invalid in-flight observation time")
    when = datetime.fromisoformat(observed_at)
    if when.tzinfo is None:
        raise ValueError("in-flight observation time requires timezone")
    clusters = result["clusters"]
    if type(clusters) is not list or not clusters:
        raise ValueError("in-flight evidence requires at least one cluster")
    cluster_ids: set[str] = set()
    for row in clusters:
        cluster = _object(
            row,
            required={"cluster_id", "allocatable", "accounting_complete", "workloads"},
        )
        cluster_id = cluster["cluster_id"]
        _identifier(cluster_id)
        if cluster_id in cluster_ids:
            raise ValueError("duplicate in-flight cluster")
        cluster_ids.add(cluster_id)
        _resources(cluster["allocatable"])
        if type(cluster["accounting_complete"]) is not bool:
            raise ValueError("in-flight accounting completeness must be boolean")
        workloads = cluster["workloads"]
        if type(workloads) is not list:
            raise ValueError("invalid in-flight workloads")
        namespaces: set[str] = set()
        for raw_workload in workloads:
            workload = _object(
                raw_workload,
                required={"namespace", "resources"},
                optional={"reservation_id", "workshop_id", "seat_refs"},
            )
            namespace = workload["namespace"]
            _identifier(namespace)
            if namespace in namespaces:
                raise ValueError("duplicate in-flight namespace")
            namespaces.add(namespace)
            _resources(workload["resources"])
            for field in ("reservation_id", "workshop_id"):
                if field in workload and workload[field] is not None:
                    _identifier(workload[field])
            seats = workload.get("seat_refs", [])
            if type(seats) is not list:
                raise ValueError("invalid in-flight seat references")
            for seat in seats:
                _identifier(seat)
            if len(seats) != len(set(seats)):
                raise ValueError("duplicate in-flight seat reference")
    return result


class FileEventInflightCapacityProvider:
    """Read a versioned server-managed JSON snapshot and derive its byte digest."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> EventInflightCapacitySnapshot:
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                raise ValueError("in-flight evidence exceeds size limit")
            document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
            validated = _validate_document(document)
            return EventInflightCapacitySnapshot.model_validate(
                {
                    "snapshot_id": "sha256:" + sha256(raw).hexdigest(),
                    "observed_at": validated["observed_at"],
                    "clusters": validated["clusters"],
                }
            )
        except (OSError, UnicodeDecodeError, ValueError, TypeError, ValidationError) as exc:
            raise EventInflightCapacityUnavailableError(
                "Configured in-flight capacity evidence is unavailable"
            ) from exc
