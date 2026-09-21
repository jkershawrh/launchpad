"""Authenticated pre-pull evidence is distinct from descriptive receipt checks."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from app.services.artifact_prepull_attestation import (
    attest_prepull_receipts,
    canonical_attestation_payload,
)


def _plan() -> dict:
    return {
        "plan_id": "sha256:" + "a" * 64,
        "event_id": "event-1",
        "not_before": "2026-09-30T14:00:00+00:00",
        "complete_by": "2026-10-01T13:30:00+00:00",
        "items": [{"cluster_ref": "arena", "image": "quay.io/example/app@sha256:" + "b" * 64}],
    }


SECRET = b"local-only-test-secret-not-for-prod"


def _envelope(plan: dict, *, secret: bytes = SECRET) -> dict:
    item = plan["items"][0]
    envelope = {
        "schema_version": "launchpad.redhat.com/event-artifact-prepull-attestation/v1",
        "plan_id": plan["plan_id"],
        "cluster_ref": "arena",
        "image": item["image"],
        "producer_id": "arena-prepull-observer",
        "observed_at": datetime(2026, 9, 30, 15, tzinfo=UTC).isoformat(),
        "mirror_source": "quay.io/example",
        "nodes": [
            {
                "node_id": "worker-a",
                "cache_state": "present",
                "digest_verified": True,
                "signature_verified": True,
                "pull_authenticated": True,
                "evidence_sha256": "sha256:" + "c" * 64,
            },
            {
                "node_id": "worker-b",
                "cache_state": "present",
                "digest_verified": True,
                "signature_verified": True,
                "pull_authenticated": True,
                "evidence_sha256": "sha256:" + "d" * 64,
            },
        ],
    }
    envelope["mac"] = hmac.new(
        secret, canonical_attestation_payload(envelope), hashlib.sha256
    ).hexdigest()
    return envelope


def _check(plan: dict, envelopes: list[dict], **kwargs: object) -> dict:
    return attest_prepull_receipts(
        plan,
        envelopes,
        trusted_producers={"arena-prepull-observer": ("arena", SECRET)},
        expected_nodes={"arena": {"worker-a", "worker-b"}},
        **kwargs,
    )


def test_authenticated_full_node_attestation_is_eligible() -> None:
    plan = _plan()
    result = _check(plan, [_envelope(plan)])
    assert result["eligible"] is True
    assert result["status"] == "GREEN-local"
    assert result["proven_items"] == 1


def test_tampered_or_unknown_producer_fails_closed() -> None:
    plan = _plan()
    tampered = _envelope(plan)
    tampered["nodes"][0]["cache_state"] = "absent"
    unknown = _envelope(plan)
    unknown["producer_id"] = "untrusted"
    assert any("MAC" in x for x in _check(plan, [tampered])["failures"])
    assert any("producer" in x for x in _check(plan, [unknown])["failures"])


def test_node_coverage_and_evidence_are_strict() -> None:
    plan = _plan()
    missing = _envelope(plan)
    missing["nodes"].pop()
    missing["mac"] = hmac.new(
        SECRET, canonical_attestation_payload(missing), hashlib.sha256
    ).hexdigest()
    assert any("node coverage" in x for x in _check(plan, [missing])["failures"])
    bogus = _envelope(plan)
    bogus["nodes"][0]["evidence_sha256"] = "not-a-digest"
    bogus["mac"] = hmac.new(
        SECRET, canonical_attestation_payload(bogus), hashlib.sha256
    ).hexdigest()
    assert any("node proof" in x for x in _check(plan, [bogus])["failures"])


def test_untrusted_inventory_and_secret_are_not_positive_evidence() -> None:
    plan = _plan()
    envelope = _envelope(plan)
    assert (
        attest_prepull_receipts(
            plan,
            [envelope],
            trusted_producers={},
            expected_nodes={"arena": {"worker-a", "worker-b"}},
        )["eligible"]
        is False
    )
    assert (
        attest_prepull_receipts(
            plan,
            [envelope],
            trusted_producers={"arena-prepull-observer": ("arena", SECRET)},
            expected_nodes={},
        )["eligible"]
        is False
    )


def test_duplicate_or_extra_attestation_fails_closed() -> None:
    plan = _plan()
    envelope = _envelope(plan)
    result = _check(plan, [envelope, envelope])
    assert result["eligible"] is False
    assert any("duplicate" in x for x in result["failures"])


def test_observation_outside_plan_window_stays_red_after_valid_mac() -> None:
    plan = _plan()
    late = _envelope(plan)
    late["observed_at"] = "2026-10-01T13:31:00+00:00"
    late["mac"] = hmac.new(SECRET, canonical_attestation_payload(late), hashlib.sha256).hexdigest()
    result = _check(plan, [late])
    assert result["eligible"] is False
    assert any("observation time" in x for x in result["failures"])


def test_signed_claim_with_unexpected_or_duplicate_node_stays_red() -> None:
    plan = _plan()
    claim = _envelope(plan)
    claim["nodes"][1]["node_id"] = "worker-a"
    claim["mac"] = hmac.new(
        SECRET, canonical_attestation_payload(claim), hashlib.sha256
    ).hexdigest()
    assert any("node coverage" in x for x in _check(plan, [claim])["failures"])
