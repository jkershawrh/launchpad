"""Deterministic, offline planning and evidence checks for event image pre-pulls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from app.services.catalog_supply_chain import IMMUTABLE_IMAGE


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_event_prepull_plan(
    *,
    event_id: str,
    starts_at: datetime,
    assignments: list[dict[str, Any]],
    artifact_report: dict[str, Any],
    lead_time_hours: int = 24,
    completion_margin_minutes: int = 30,
) -> dict[str, Any]:
    """Build one immutable, deduplicated pre-pull plan from approved assignments."""

    if starts_at.tzinfo is None:
        raise ValueError("event starts_at must include a timezone")
    if not event_id.strip() or not assignments:
        raise ValueError("event ID and at least one workshop assignment are required")
    if artifact_report.get("status") != "GREEN-local" or artifact_report.get("violations"):
        raise ValueError("artifact report must be locally green without violations")

    catalogs = artifact_report.get("catalogs") or {}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for assignment in assignments:
        cluster_ref = str(assignment.get("cluster_ref", "")).strip()
        workshop_id = str(assignment.get("workshop_id", "")).strip()
        catalog_id = str(assignment.get("catalog_id", "")).strip()
        if not cluster_ref or not workshop_id or not catalog_id:
            raise ValueError("every assignment requires cluster_ref, workshop_id, and catalog_id")
        catalog = catalogs.get(catalog_id)
        if not isinstance(catalog, dict) or catalog.get("violations"):
            raise ValueError(f"catalog is absent or ineligible for pre-pull: {catalog_id}")
        images = catalog.get("images") or []
        if not images:
            raise ValueError(f"catalog has no immutable images to pre-pull: {catalog_id}")
        for image in images:
            if not IMMUTABLE_IMAGE.fullmatch(str(image)):
                raise ValueError(f"pre-pull image is not immutable: {image}")
            key = (cluster_ref, str(image))
            item = grouped.setdefault(
                key,
                {
                    "cluster_ref": cluster_ref,
                    "image": str(image),
                    "catalog_ids": set(),
                    "workshop_ids": set(),
                },
            )
            item["catalog_ids"].add(catalog_id)
            item["workshop_ids"].add(workshop_id)

    items = [
        {
            **item,
            "catalog_ids": sorted(item["catalog_ids"]),
            "workshop_ids": sorted(item["workshop_ids"]),
        }
        for _, item in sorted(grouped.items())
    ]
    payload = {
        "schema_version": "launchpad.redhat.com/event-artifact-prepull/v1",
        "event_id": event_id,
        "event_starts_at": starts_at.isoformat(),
        "not_before": (starts_at - timedelta(hours=lead_time_hours)).isoformat(),
        "complete_by": (
            starts_at - timedelta(minutes=completion_margin_minutes)
        ).isoformat(),
        "artifact_policy": artifact_report.get("policy"),
        "items": items,
    }
    return {"plan_id": _digest(payload), **payload}


def evaluate_prepull_receipts(
    plan: dict[str, Any],
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fail closed unless every planned cluster/image pair has fresh full-node proof."""

    expected = {
        (item["cluster_ref"], item["image"]): item for item in plan.get("items") or []
    }
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    failures: list[str] = []
    for receipt in receipts:
        if receipt.get("schema_version") != (
            "launchpad.redhat.com/event-artifact-prepull-receipt/v1"
        ):
            failures.append("receipt schema is unsupported")
            continue
        if receipt.get("plan_id") != plan.get("plan_id"):
            failures.append("receipt plan_id does not match the immutable plan")
            continue
        key = (str(receipt.get("cluster_ref", "")), str(receipt.get("image", "")))
        if key not in expected:
            failures.append(f"receipt is not part of the plan: {key[0]} {key[1]}")
            continue
        if key in by_key:
            failures.append(f"duplicate receipt: {key[0]} {key[1]}")
            continue
        by_key[key] = receipt

    for key in sorted(expected):
        receipt = by_key.get(key)
        label = f"{key[0]} {key[1]}"
        if receipt is None:
            failures.append(f"pre-pull receipt is missing: {label}")
            continue
        if receipt.get("status") != "passed":
            failures.append(f"pre-pull did not pass: {label}")
        if receipt.get("cache_state") != "present":
            failures.append(f"image cache is not present: {label}")
        if receipt.get("digest_verified") is not True:
            failures.append(f"image digest is not verified: {label}")
        if receipt.get("signature_verified") is not True:
            failures.append(f"image signature is not verified: {label}")
        if not str(receipt.get("mirror_source", "")).strip():
            failures.append(f"mirror/source attribution is missing: {label}")
        ready = receipt.get("nodes_ready")
        expected_nodes = receipt.get("nodes_expected")
        if not isinstance(ready, int) or not isinstance(expected_nodes, int) or ready < 1:
            failures.append(f"node coverage is invalid: {label}")
        elif ready != expected_nodes:
            failures.append(f"node coverage is incomplete: {label}")
        if not receipt.get("evidence"):
            failures.append(f"pre-pull evidence is missing: {label}")

    return {
        "schema_version": "launchpad.redhat.com/event-artifact-prepull-status/v1",
        "plan_id": plan.get("plan_id"),
        "event_id": plan.get("event_id"),
        "status": "GREEN-integration" if not failures else "RED",
        "eligible": not failures,
        "planned_items": len(expected),
        "proven_items": len(by_key),
        "failures": failures,
    }
