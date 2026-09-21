"""Bounded, offline verification of pre-pull proof bytes and node inventory.

The existing HMAC attestation verifies claims. This additional layer retrieves
the claimed immutable proof bytes from an injected read-only store, hashes and
parses them, and binds claims to a separately sourced fresh node inventory.
Neither layer observes Kubernetes or is wired to live admission.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from app.services.artifact_prepull_attestation import attest_prepull_receipts

PROOF_SCHEMA = "launchpad.redhat.com/event-artifact-node-proof/v1"
INVENTORY_SCHEMA = "launchpad.redhat.com/eligible-node-snapshot/v1"
STATUS_SCHEMA = "launchpad.redhat.com/event-artifact-prepull-evidence-status/v1"
MAX_CLAIMS = 256
MAX_NODES_PER_CLAIM = 1024
MAX_PROOF_BYTES = 65536
MAX_INVENTORY_AGE = timedelta(minutes=5)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PROOF_KEYS = frozenset(
    {
        "schema_version",
        "plan_id",
        "cluster_ref",
        "image",
        "node_id",
        "producer_id",
        "observed_at",
        "mirror_source",
        "cache_state",
        "digest_verified",
        "signature_verified",
        "pull_authenticated",
    }
)
_INVENTORY_KEYS = frozenset(
    {
        "schema_version",
        "cluster_ref",
        "source_id",
        "observed_at",
        "complete",
        "resource_version",
        "node_ids",
    }
)


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _inventory(
    cluster: str,
    snapshot: object,
    trusted_sources: Mapping[str, str],
    producer_ids: set[str],
    as_of: datetime,
    not_before: datetime,
    complete_by: datetime,
) -> tuple[set[str] | None, str | None]:
    if not isinstance(snapshot, dict) or set(snapshot) != _INVENTORY_KEYS:
        return None, f"eligible-node inventory is missing or malformed: {cluster}"
    source = snapshot["source_id"]
    expected_source = trusted_sources.get(cluster)
    if (
        snapshot["schema_version"] != INVENTORY_SCHEMA
        or snapshot["cluster_ref"] != cluster
        or not isinstance(source, str)
        or not source
        or not isinstance(expected_source, str)
        or not expected_source
        or source != expected_source
        or source in producer_ids
        or snapshot["complete"] is not True
        or not isinstance(snapshot["resource_version"], str)
        or not snapshot["resource_version"].strip()
    ):
        return None, f"eligible-node inventory source/completeness is invalid: {cluster}"
    observed = _time(snapshot["observed_at"])
    if (
        observed is None
        or not not_before <= observed <= complete_by
        or not timedelta(0) <= as_of - observed <= MAX_INVENTORY_AGE
    ):
        return None, f"eligible-node inventory is stale, future, or outside plan: {cluster}"
    nodes = snapshot["node_ids"]
    if (
        not isinstance(nodes, list)
        or not 0 < len(nodes) <= MAX_NODES_PER_CLAIM
        or any(not isinstance(node, str) or not node.strip() for node in nodes)
        or len(nodes) != len(set(nodes))
    ):
        return None, f"eligible-node inventory coverage is invalid: {cluster}"
    return set(nodes), None


def verify_prepull_evidence(
    plan: dict[str, Any],
    envelopes: list[dict[str, Any]],
    *,
    inventory_snapshots: Mapping[str, dict[str, Any]],
    trusted_inventory_sources: Mapping[str, str],
    trusted_producers: Mapping[str, tuple[str, bytes]],
    evidence_store: Mapping[str, bytes],
    as_of: datetime,
) -> dict[str, Any]:
    """Verify claim bytes and independent inventory, with no live side effects.

    Callers must inject a trusted snapshot adapter and an immutable content
    store. The source-ID binding here is only as trustworthy as that adapter;
    self-declared source IDs are not authoritative evidence.
    """

    failures: list[str] = []
    verified_node_proofs = 0
    if not isinstance(plan, dict) or not isinstance(envelopes, list):
        failures.append("plan or claims are invalid")
    elif not 0 < len(envelopes) <= MAX_CLAIMS or not isinstance(plan.get("items"), list):
        failures.append("plan or claim count is empty or exceeds bounds")
    elif not 0 < len(plan["items"]) <= MAX_CLAIMS:
        failures.append("plan item count is empty or exceeds bounds")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        failures.append("verification time must include timezone")
    not_before = _time(plan.get("not_before")) if isinstance(plan, dict) else None
    complete_by = _time(plan.get("complete_by")) if isinstance(plan, dict) else None
    if not_before is None or complete_by is None or not_before > complete_by:
        failures.append("plan observation window is invalid")
    if failures:
        return _result(plan, failures, 0)

    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("cluster_ref"), str)
        or not item["cluster_ref"]
        for item in plan["items"]
    ):
        return _result(plan, ["planned clusters are invalid"], 0)
    clusters = {item["cluster_ref"] for item in plan["items"]}
    if not isinstance(inventory_snapshots, Mapping):
        return _result(plan, ["independent node inventories are invalid"], 0)
    if set(inventory_snapshots) != clusters:
        return _result(plan, ["independent node inventories do not cover exact clusters"], 0)
    producer_ids = set(trusted_producers)
    expected_nodes: dict[str, set[str]] = {}
    for cluster in sorted(clusters):
        nodes, error = _inventory(
            cluster,
            inventory_snapshots[cluster],
            trusted_inventory_sources,
            producer_ids,
            as_of,
            not_before,
            complete_by,
        )
        if error:
            failures.append(error)
        elif nodes is not None:
            expected_nodes[cluster] = nodes
    if failures:
        return _result(plan, failures, 0)

    try:
        attested = attest_prepull_receipts(
            plan, envelopes, trusted_producers=trusted_producers, expected_nodes=expected_nodes
        )
    except (KeyError, TypeError, ValueError):
        return _result(plan, ["attestation inputs are malformed"], 0)
    failures.extend(attested["failures"])
    if failures:
        return _result(plan, failures, 0)

    for envelope in envelopes:
        cluster = envelope["cluster_ref"]
        image = envelope["image"]
        if not 0 < len(envelope["nodes"]) <= MAX_NODES_PER_CLAIM:
            failures.append(f"node proof count exceeds bounds: {cluster} {image}")
            continue
        observed = _time(envelope["observed_at"])
        if observed is None or not timedelta(0) <= as_of - observed <= MAX_INVENTORY_AGE:
            failures.append(f"attestation is stale or future-dated: {cluster} {image}")
            continue
        for node in envelope["nodes"]:
            node_id = node["node_id"]
            digest = node["evidence_sha256"]
            label = f"{cluster} {image} {node_id}"
            if not _DIGEST.fullmatch(digest):
                failures.append(f"node evidence digest is invalid: {label}")
                continue
            try:
                raw = evidence_store[digest]
            except Exception:  # noqa: BLE001 - injected store failures may contain secrets
                failures.append(f"node evidence bytes are unavailable: {label}")
                continue
            if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_PROOF_BYTES:
                failures.append(f"node evidence bytes are invalid or oversized: {label}")
                continue
            if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
                failures.append(f"node evidence digest mismatch: {label}")
                continue
            try:
                proof = json.loads(raw, object_pairs_hook=_unique_object)
            except (UnicodeDecodeError, ValueError):
                failures.append(f"node evidence JSON is invalid: {label}")
                continue
            expected = {
                "schema_version": PROOF_SCHEMA,
                "plan_id": plan["plan_id"],
                "cluster_ref": cluster,
                "image": image,
                "node_id": node_id,
                "producer_id": envelope["producer_id"],
                "observed_at": envelope["observed_at"],
                "mirror_source": envelope["mirror_source"],
                "cache_state": "present",
                "digest_verified": True,
                "signature_verified": True,
                "pull_authenticated": True,
            }
            if (
                not isinstance(proof, dict)
                or set(proof) != _PROOF_KEYS
                or proof != expected
                or any(
                    proof[field] is not True
                    for field in ("digest_verified", "signature_verified", "pull_authenticated")
                )
            ):
                failures.append(f"node evidence identity or proof mismatches claim: {label}")
                continue
            verified_node_proofs += 1
    return _result(plan, failures, verified_node_proofs)


def _result(plan: object, failures: list[str], verified: int) -> dict[str, Any]:
    return {
        "schema_version": STATUS_SCHEMA,
        "plan_id": plan.get("plan_id") if isinstance(plan, dict) else None,
        "status": "GREEN-local" if not failures else "RED",
        "eligible": not failures,
        "verified_node_proofs": verified,
        "failures": failures,
    }
