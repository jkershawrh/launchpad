"""Check a retained-workshop inventory envelope before citing its counts.

This is an internal consistency check, not independent source verification,
participant-journey proof, or authorization to reclaim a workshop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RetainedInventoryResult:
    workshops: int
    seats: int
    active_entitlements: int


def _object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} has an invalid shape")
    return value


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def validate_retained_inventory_evidence(payload: Any) -> RetainedInventoryResult:
    """Reject inconsistent, premature, or unexpected-field interim evidence."""
    root = _object(
        payload,
        {
            "schema_version",
            "observed_at",
            "purpose",
            "not_a_reclaim_authorization",
            "sources",
            "summary",
            "workshops",
            "limitations",
        },
        "evidence",
    )
    if root["schema_version"] != 1 or root["not_a_reclaim_authorization"] is not True:
        raise ValueError("evidence is not marked as a non-authorizing interim observation")
    observed_at = _timestamp(root["observed_at"], "observed_at")
    if (
        not isinstance(root["purpose"], str)
        or not root["purpose"]
        or not isinstance(root["sources"], list)
        or len(root["sources"]) < 2
        or any(not isinstance(item, str) or not item for item in root["sources"])
        or not isinstance(root["limitations"], list)
        or not root["limitations"]
        or any(not isinstance(item, str) or not item for item in root["limitations"])
    ):
        raise ValueError("evidence provenance or limitations are missing")
    summary = _object(
        root["summary"],
        {
            "workshops_ready",
            "sessions_ready",
            "active_entitlements",
            "unclaimed_seats",
            "labeled_namespaces_present",
            "clusters",
        },
        "summary",
    )
    if not isinstance(root["workshops"], list) or not root["workshops"]:
        raise ValueError("workshop roster is empty or invalid")
    workshop_ids: set[str] = set()
    seats = claims = 0
    by_cluster: dict[str, int] = {}
    for item in root["workshops"]:
        workshop = _object(
            item,
            {
                "workshop_id",
                "cluster_ref",
                "catalog",
                "sessions_ready",
                "active_entitlements",
                "expires_at",
            },
            "workshop",
        )
        workshop_id = workshop["workshop_id"]
        try:
            if str(UUID(workshop_id)) != workshop_id:
                raise ValueError
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("workshop_id is not a canonical UUID") from exc
        if workshop_id in workshop_ids:
            raise ValueError("duplicate workshop_id")
        workshop_ids.add(workshop_id)
        cluster = workshop["cluster_ref"]
        if (
            not isinstance(cluster, str)
            or not cluster
            or not isinstance(workshop["catalog"], str)
            or not workshop["catalog"]
        ):
            raise ValueError("workshop identity is incomplete")
        session_count = _count(workshop["sessions_ready"], "sessions_ready")
        claim_count = _count(workshop["active_entitlements"], "active_entitlements")
        if session_count == 0 or claim_count > session_count:
            raise ValueError("workshop claim count exceeds its seats")
        if _timestamp(workshop["expires_at"], "expires_at") <= observed_at:
            raise ValueError("retained workshop expired before observation")
        seats += session_count
        claims += claim_count
        by_cluster[cluster] = by_cluster.get(cluster, 0) + session_count

    if (
        _count(summary["workshops_ready"], "workshops_ready") != len(workshop_ids)
        or _count(summary["sessions_ready"], "sessions_ready") != seats
        or _count(summary["active_entitlements"], "active_entitlements") != claims
        or _count(summary["unclaimed_seats"], "unclaimed_seats") != seats - claims
        or _count(summary["labeled_namespaces_present"], "labeled_namespaces_present") != seats
    ):
        raise ValueError("summary does not balance against workshop records")
    clusters = summary["clusters"]
    if not isinstance(clusters, dict) or set(clusters) != set(by_cluster):
        raise ValueError("cluster summary does not cover the workshop roster")
    for cluster, expected in by_cluster.items():
        row = _object(
            clusters[cluster], {"sessions_ready", "labeled_namespaces_present"}, "cluster"
        )
        if (
            _count(row["sessions_ready"], "cluster sessions_ready") != expected
            or _count(row["labeled_namespaces_present"], "cluster labeled_namespaces_present")
            != expected
        ):
            raise ValueError("cluster summary does not balance")
    return RetainedInventoryResult(len(workshop_ids), seats, claims)
