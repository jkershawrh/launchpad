"""Authenticate one catalog render review without granting release authority.

The trusted producer key is supplied by the caller from an external secret
store. Nothing in this module renders a chart, reads a cluster, or persists a
key. A valid MAC proves only that the named producer signed the exact bounded
claim; candidate admission and live certification remain separate gates.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

SCHEMA = "launchpad.redhat.com/catalog-intake-render-attestation/v1"
STATUS_SCHEMA = "launchpad.redhat.com/catalog-intake-render-attestation-status/v1"

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_MAC = re.compile(r"[0-9a-f]{64}\Z")
_BINDING_FIELDS = (
    "catalog_item_id",
    "source_revision",
    "helm_values_sha256",
    "manifest_sha256",
    "renderer_image_digest",
    "render_review_sha256",
)
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "producer_id",
        "observed_at",
        *_BINDING_FIELDS,
        "network_egress_denied",
        "workspace_removed",
        "mac",
    }
)


def canonical_render_attestation_payload(envelope: Mapping[str, Any]) -> bytes:
    """Return deterministic signed bytes, excluding the MAC itself."""

    return json.dumps(
        {key: value for key, value in envelope.items() if key != "mac"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def _valid_expected(expected: Mapping[str, Any]) -> bool:
    if set(expected) != set(_BINDING_FIELDS):
        return False
    return (
        isinstance(expected["catalog_item_id"], str)
        and bool(expected["catalog_item_id"])
        and isinstance(expected["source_revision"], str)
        and _REVISION.fullmatch(expected["source_revision"]) is not None
        and all(
            isinstance(expected[field], str) and _DIGEST.fullmatch(expected[field]) is not None
            for field in _BINDING_FIELDS[2:]
        )
    )


def _result(envelope: Mapping[str, Any], findings: set[str]) -> dict[str, Any]:
    authenticated = not findings
    return {
        "schema_version": STATUS_SCHEMA,
        "status": "GREEN-local-authenticated" if authenticated else "RED",
        "authenticated": authenticated,
        "producer_id": envelope.get("producer_id") if authenticated else None,
        "catalog_item_id": envelope.get("catalog_item_id"),
        "source_revision": envelope.get("source_revision"),
        "render_review_sha256": envelope.get("render_review_sha256"),
        "findings": sorted(findings),
        "release_eligible": False,
    }


def verify_render_attestation(
    envelope: Mapping[str, Any] | None,
    *,
    expected: Mapping[str, Any],
    trusted_producers: Mapping[str, bytes],
) -> dict[str, Any]:
    """Verify one exact render claim using externally supplied producer trust."""

    findings: set[str] = set()
    if not isinstance(envelope, Mapping) or set(envelope) != _ENVELOPE_FIELDS:
        return _result(envelope or {}, {"attestation-fields-invalid"})
    if envelope.get("schema_version") != SCHEMA:
        findings.add("attestation-schema-invalid")
    if not _valid_expected(expected):
        findings.add("expected-binding-invalid")
    elif any(envelope.get(field) != expected[field] for field in _BINDING_FIELDS):
        findings.add("attestation-binding-mismatch")

    producer_id = envelope.get("producer_id")
    producer_key = trusted_producers.get(producer_id) if isinstance(producer_id, str) else None
    if not isinstance(producer_key, bytes) or len(producer_key) < 16:
        findings.add("trusted-producer-unavailable")
    else:
        mac = envelope.get("mac")
        if not isinstance(mac, str) or _MAC.fullmatch(mac) is None:
            findings.add("attestation-mac-invalid")
        else:
            try:
                actual = hmac.new(
                    producer_key,
                    canonical_render_attestation_payload(envelope),
                    hashlib.sha256,
                ).hexdigest()
            except (TypeError, ValueError):
                findings.add("attestation-payload-invalid")
            else:
                if not hmac.compare_digest(mac, actual):
                    findings.add("attestation-mac-invalid")

    if not _aware_timestamp(envelope.get("observed_at")):
        findings.add("attestation-time-invalid")
    if (
        envelope.get("network_egress_denied") is not True
        or envelope.get("workspace_removed") is not True
    ):
        findings.add("render-isolation-unverified")
    return _result(envelope, findings)
