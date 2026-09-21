"""Offline, fail-closed authentication of destination image pre-pull receipts.

This verifies a designated observer's MAC over per-node claims. It does not
observe Kubernetes, pull an image, or establish that the observer is deployed.
Callers must obtain producer keys and eligible-node inventory independently.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.services.artifact_prepull import evaluate_prepull_receipts

SCHEMA = "launchpad.redhat.com/event-artifact-prepull-attestation/v1"
RECEIPT_SCHEMA = "launchpad.redhat.com/event-artifact-prepull-receipt/v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAC = re.compile(r"[0-9a-f]{64}\Z")
_ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "plan_id",
        "cluster_ref",
        "image",
        "producer_id",
        "observed_at",
        "mirror_source",
        "nodes",
        "mac",
    }
)
_NODE_KEYS = frozenset(
    {
        "node_id",
        "cache_state",
        "digest_verified",
        "signature_verified",
        "pull_authenticated",
        "evidence_sha256",
    }
)


def canonical_attestation_payload(envelope: Mapping[str, Any]) -> bytes:
    """Canonical signed bytes; the ``mac`` field itself is excluded."""

    return json.dumps(
        {key: value for key, value in envelope.items() if key != "mac"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _aware(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def attest_prepull_receipts(
    plan: dict[str, Any],
    envelopes: list[dict[str, Any]],
    *,
    trusted_producers: Mapping[str, tuple[str, bytes]],
    expected_nodes: Mapping[str, set[str]],
) -> dict[str, Any]:
    """Authenticate every planned cluster/image claim and verify node coverage.

    ``trusted_producers`` binds each producer ID to one cluster and a key loaded
    from an external secret store. ``expected_nodes`` is a separate, fresh,
    authoritative eligible-node snapshot; absence is never interpreted as zero.
    """

    failures: list[str] = []
    expected: set[tuple[str, str]] = set()
    for item in plan.get("items") or []:
        if not isinstance(item, dict):
            failures.append("plan item is invalid")
            continue
        key = (item.get("cluster_ref"), item.get("image"))
        if not all(isinstance(part, str) and part for part in key) or key in expected:
            failures.append("plan item is invalid or duplicated")
            continue
        expected.add(key)
    if not expected or not isinstance(plan.get("plan_id"), str):
        failures.append("immutable plan is missing or invalid")

    seen: set[tuple[str, str]] = set()
    verified: list[dict[str, Any]] = []
    for envelope in envelopes:
        if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_KEYS:
            failures.append("attestation fields are invalid")
            continue
        key = (envelope["cluster_ref"], envelope["image"])
        if not all(isinstance(part, str) and part for part in key):
            failures.append("attestation cluster/image is invalid")
            continue
        if key not in expected:
            failures.append("attestation is not part of the plan")
            continue
        if key in seen:
            failures.append(f"duplicate attestation: {key[0]} {key[1]}")
            continue
        seen.add(key)
        label = f"{key[0]} {key[1]}"
        if envelope["schema_version"] != SCHEMA or envelope["plan_id"] != plan["plan_id"]:
            failures.append(f"attestation schema or plan mismatch: {label}")
            continue
        producer_id = envelope["producer_id"]
        producer = trusted_producers.get(producer_id) if isinstance(producer_id, str) else None
        if (
            not isinstance(producer, tuple)
            or len(producer) != 2
            or producer[0] != key[0]
            or not isinstance(producer[1], bytes)
            or len(producer[1]) < 16
        ):
            failures.append(f"trusted producer is unavailable or cluster-mismatched: {label}")
            continue
        mac = envelope["mac"]
        if not isinstance(mac, str) or not _MAC.fullmatch(mac):
            failures.append(f"attestation MAC is invalid: {label}")
            continue
        try:
            actual = hmac.new(
                producer[1], canonical_attestation_payload(envelope), hashlib.sha256
            ).hexdigest()
        except (TypeError, ValueError):
            failures.append(f"attestation payload is invalid: {label}")
            continue
        if not hmac.compare_digest(mac, actual):
            failures.append(f"attestation MAC verification failed: {label}")
            continue
        if not _aware(envelope["observed_at"]):
            failures.append(f"attestation observation time is invalid: {label}")
            continue
        mirror = envelope["mirror_source"]
        if not isinstance(mirror, str) or not mirror.strip():
            failures.append(f"attestation mirror/source is missing: {label}")
            continue
        inventory = expected_nodes.get(key[0])
        if (
            not isinstance(inventory, set)
            or not inventory
            or not all(isinstance(node, str) and node for node in inventory)
        ):
            failures.append(f"trusted node inventory is unavailable: {label}")
            continue
        nodes = envelope["nodes"]
        if not isinstance(nodes, list) or not nodes or not all(isinstance(n, dict) for n in nodes):
            failures.append(f"node coverage is invalid: {label}")
            continue
        node_ids = [node.get("node_id") for node in nodes]
        if (
            not all(isinstance(node_id, str) and node_id for node_id in node_ids)
            or len(node_ids) != len(inventory)
            or set(node_ids) != inventory
        ):
            failures.append(f"node coverage is incomplete or unexpected: {label}")
            continue
        valid_nodes = all(
            set(node) == _NODE_KEYS
            and node["cache_state"] == "present"
            and node["digest_verified"] is True
            and node["signature_verified"] is True
            and node["pull_authenticated"] is True
            and isinstance(node["evidence_sha256"], str)
            and _DIGEST.fullmatch(node["evidence_sha256"]) is not None
            for node in nodes
        )
        if not valid_nodes:
            failures.append(f"node proof is incomplete or invalid: {label}")
            continue
        verified.append(
            {
                "schema_version": RECEIPT_SCHEMA,
                "plan_id": plan["plan_id"],
                "cluster_ref": key[0],
                "image": key[1],
                "status": "passed",
                "cache_state": "present",
                "digest_verified": True,
                "signature_verified": True,
                "mirror_source": mirror,
                "nodes_expected": len(inventory),
                "nodes_ready": len(nodes),
                "observed_at": envelope["observed_at"],
                "evidence": [node["evidence_sha256"] for node in nodes],
            }
        )

    descriptive = evaluate_prepull_receipts(plan, verified)
    failures.extend(descriptive["failures"])
    return {
        "schema_version": "launchpad.redhat.com/event-artifact-prepull-attestation-status/v1",
        "plan_id": plan.get("plan_id"),
        "status": "GREEN-local" if not failures else "RED",
        "eligible": not failures,
        "planned_items": len(expected),
        "proven_items": len(verified),
        "failures": failures,
    }
