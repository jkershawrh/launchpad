"""Aggregate sanitized operational receipts into the VEF v1alpha2 input shape."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SCHEMA = "launchpad.vef-aggregate-receipt.v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STATES = {"unavailable", "partial", "authoritative"}
_SENSITIVE = {
    "email",
    "prompt",
    "response",
    "participant_id",
    "participant",
    "namespace",
    "cluster",
    "credential",
    "secret",
    "api_key",
}
_REQUIRED_SINGLE = {"platform_lifecycle", "ai_usage", "cost_allocation"}
_SINGLE_FIELDS = {
    "ai_usage": {
        "measurement_state",
        "actual_requests",
        "input_tokens",
        "output_tokens",
        "inference_cost_usd",
    },
    "platform_lifecycle": {
        "measurement_state",
        "orders_requested",
        "seats_requested",
        "seats_ready",
        "seats_reclaimed",
        "provisioning_p95_seconds",
        "reclaim_p95_seconds",
        "human_interventions",
        "residue_count",
    },
    "cost_allocation": {
        "measurement_state",
        "allocation_basis",
        "shared_platform_cost_usd",
        "delivery_cost_usd",
        "allocated_inference_cost_usd",
        "unallocated_cost_usd",
        "cost_center_ready",
        "chargeback_ready",
    },
}


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _SENSITIVE:
                raise ValueError("sensitive field is prohibited in VEF telemetry")
            _reject_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive(child)


def _measurement(data: dict[str, Any], fields: tuple[str, ...]) -> None:
    state = data.get("measurement_state")
    if state not in _STATES:
        raise ValueError("measurement state is invalid")
    if state == "authoritative" and any(data.get(field) is None for field in fields):
        raise ValueError("authoritative receipt cannot contain unknown values")


def aggregate_vef_receipts(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Return only bounded aggregates; raw receipts and identities are not exported."""

    if not isinstance(receipts, list) or not receipts:
        raise ValueError("required receipt set is missing")
    _reject_sensitive(receipts)
    seen: set[str] = set()
    pilot_id: str | None = None
    singles: dict[str, dict[str, Any]] = {}
    tracks: list[dict[str, Any]] = []
    track_ids: set[str] = set()
    sources: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, dict) or set(receipt) != {
            "schema_version",
            "pilot_id",
            "receipt_id",
            "kind",
            "data",
        }:
            raise ValueError("receipt fields are invalid")
        if receipt["schema_version"] != SCHEMA:
            raise ValueError("receipt schema is invalid")
        if pilot_id is None:
            pilot_id = receipt["pilot_id"]
        if not isinstance(pilot_id, str) or not pilot_id or receipt["pilot_id"] != pilot_id:
            raise ValueError("receipt pilot identity mismatch")
        receipt_id = receipt["receipt_id"]
        if not isinstance(receipt_id, str) or _DIGEST.fullmatch(receipt_id) is None:
            raise ValueError("receipt identity is invalid")
        if receipt_id in seen:
            raise ValueError("duplicate receipt identity")
        seen.add(receipt_id)
        sources.append(receipt_id)
        kind = receipt["kind"]
        data = receipt["data"]
        if not isinstance(data, dict):
            raise TypeError("receipt data is invalid")
        if kind == "track_outcome":
            track_id = data.get("track_id")
            if not isinstance(track_id, str) or not track_id or track_id in track_ids:
                raise ValueError("duplicate or invalid track outcome")
            required = {
                "track_id",
                "provisioned_seats",
                "activated_journeys",
                "successful_journeys",
                "failed_journeys",
                "unknown_outcomes",
                "evidence_state",
            }
            if set(data) != required or data["evidence_state"] not in _STATES:
                raise ValueError("track outcome fields are invalid")
            counts = [data[field] for field in required - {"track_id", "evidence_state"}]
            if not all(isinstance(value, int) and value >= 0 for value in counts):
                raise ValueError("track outcome counts are invalid")
            if (
                data["activated_journeys"]
                != data["successful_journeys"] + data["failed_journeys"] + data["unknown_outcomes"]
                or data["activated_journeys"] > data["provisioned_seats"]
            ):
                raise ValueError("track outcome counts do not reconcile")
            track_ids.add(track_id)
            tracks.append(dict(data))
        elif kind in _REQUIRED_SINGLE:
            if kind in singles:
                raise ValueError("duplicate receipt kind")
            if set(data) != _SINGLE_FIELDS[kind]:
                raise ValueError("receipt data fields are invalid")
            singles[kind] = dict(data)
        else:
            raise ValueError("receipt kind is invalid")
    if not tracks or set(singles) != _REQUIRED_SINGLE:
        raise ValueError("required receipt set is incomplete")
    _measurement(
        singles["ai_usage"],
        ("actual_requests", "input_tokens", "output_tokens", "inference_cost_usd"),
    )
    _measurement(
        singles["platform_lifecycle"],
        (
            "orders_requested",
            "seats_requested",
            "seats_ready",
            "seats_reclaimed",
            "provisioning_p95_seconds",
            "reclaim_p95_seconds",
            "human_interventions",
            "residue_count",
        ),
    )
    _measurement(
        singles["cost_allocation"],
        (
            "shared_platform_cost_usd",
            "delivery_cost_usd",
            "allocated_inference_cost_usd",
            "unallocated_cost_usd",
            "cost_center_ready",
            "chargeback_ready",
        ),
    )
    return {
        "status": "ready",
        "pilot_id": pilot_id,
        "ai_usage": singles["ai_usage"],
        "analytics": {
            "track_outcomes": sorted(tracks, key=lambda item: item["track_id"]),
            "platform_lifecycle": singles["platform_lifecycle"],
            "cost_allocation": singles["cost_allocation"],
        },
        "evidence_sources": sorted(sources),
    }
