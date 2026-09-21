"""Offline byte and independent-inventory checks for pre-pull claims."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from app.services.artifact_prepull_attestation import canonical_attestation_payload
from app.services.artifact_prepull_evidence import verify_prepull_evidence

SECRET = b"local-test-producer-key-not-for-production"
OBSERVED = datetime(2026, 9, 30, 15, tzinfo=UTC)
IMAGE = "quay.io/example/app@sha256:" + "b" * 64


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fixture() -> tuple[dict, list[dict], dict, dict]:
    plan = {
        "plan_id": "sha256:" + "a" * 64,
        "event_id": "event-1",
        "not_before": "2026-09-30T14:00:00+00:00",
        "complete_by": "2026-10-01T13:30:00+00:00",
        "items": [{"cluster_ref": "arena", "image": IMAGE}],
    }
    evidence = {}
    nodes = []
    for name in ("worker-a", "worker-b"):
        artifact = {
            "schema_version": "launchpad.redhat.com/event-artifact-node-proof/v1",
            "plan_id": plan["plan_id"],
            "cluster_ref": "arena",
            "image": IMAGE,
            "node_id": name,
            "producer_id": "arena-prepull-observer",
            "observed_at": OBSERVED.isoformat(),
            "mirror_source": "quay.io/example",
            "cache_state": "present",
            "digest_verified": True,
            "signature_verified": True,
            "pull_authenticated": True,
        }
        raw = _canonical(artifact)
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        evidence[digest] = raw
        nodes.append(
            {
                "node_id": name,
                "cache_state": "present",
                "digest_verified": True,
                "signature_verified": True,
                "pull_authenticated": True,
                "evidence_sha256": digest,
            }
        )
    envelope = {
        "schema_version": "launchpad.redhat.com/event-artifact-prepull-attestation/v1",
        "plan_id": plan["plan_id"],
        "cluster_ref": "arena",
        "image": IMAGE,
        "producer_id": "arena-prepull-observer",
        "observed_at": OBSERVED.isoformat(),
        "mirror_source": "quay.io/example",
        "nodes": nodes,
    }
    envelope["mac"] = hmac.new(
        SECRET, canonical_attestation_payload(envelope), hashlib.sha256
    ).hexdigest()
    inventory = {
        "arena": {
            "schema_version": "launchpad.redhat.com/eligible-node-snapshot/v1",
            "cluster_ref": "arena",
            "source_id": "arena-scheduler-inventory",
            "observed_at": OBSERVED.isoformat(),
            "complete": True,
            "resource_version": "12345",
            "node_ids": ["worker-a", "worker-b"],
        }
    }
    return plan, [envelope], inventory, evidence


def _check(plan, envelopes, inventory, evidence, *, as_of=OBSERVED):
    return verify_prepull_evidence(
        plan,
        envelopes,
        inventory_snapshots=inventory,
        trusted_inventory_sources={"arena": "arena-scheduler-inventory"},
        trusted_producers={"arena-prepull-observer": ("arena", SECRET)},
        evidence_store=evidence,
        as_of=as_of,
    )


def test_exact_bytes_and_independent_fresh_inventory_pass_local_only():
    plan, envelopes, inventory, evidence = _fixture()
    report = _check(plan, envelopes, inventory, evidence)
    assert report["eligible"] is True
    assert report["status"] == "GREEN-local"
    assert report["verified_node_proofs"] == 2


def test_missing_corrupt_or_wrong_identity_evidence_fails_closed():
    plan, envelopes, inventory, evidence = _fixture()
    missing = dict(evidence)
    missing.pop(envelopes[0]["nodes"][0]["evidence_sha256"])
    assert not _check(plan, envelopes, inventory, missing)["eligible"]
    corrupt = dict(evidence)
    corrupt[envelopes[0]["nodes"][0]["evidence_sha256"]] = b"{}"
    assert any("digest" in x for x in _check(plan, envelopes, inventory, corrupt)["failures"])
    wrong = dict(evidence)
    raw = next(iter(evidence.values()))
    proof = json.loads(raw)
    proof["node_id"] = "worker-other"
    changed = _canonical(proof)
    changed_digest = "sha256:" + hashlib.sha256(changed).hexdigest()
    old_digest = envelopes[0]["nodes"][0]["evidence_sha256"]
    wrong.pop(old_digest)
    wrong[changed_digest] = changed
    envelopes[0]["nodes"][0]["evidence_sha256"] = changed_digest
    envelopes[0]["mac"] = hmac.new(
        SECRET, canonical_attestation_payload(envelopes[0]), hashlib.sha256
    ).hexdigest()
    assert any("identity" in x for x in _check(plan, envelopes, inventory, wrong)["failures"])


def test_inventory_source_completeness_and_freshness_fail_closed():
    plan, envelopes, inventory, evidence = _fixture()
    inventory["arena"]["source_id"] = "arena-prepull-observer"
    assert not _check(plan, envelopes, inventory, evidence)["eligible"]
    inventory["arena"]["source_id"] = "arena-scheduler-inventory"
    inventory["arena"]["complete"] = False
    assert not _check(plan, envelopes, inventory, evidence)["eligible"]
    inventory["arena"]["complete"] = True
    assert not _check(plan, envelopes, inventory, evidence, as_of=OBSERVED + timedelta(minutes=6))[
        "eligible"
    ]


def test_oversize_evidence_and_unbounded_claim_set_fail_closed():
    plan, envelopes, inventory, evidence = _fixture()
    digest = envelopes[0]["nodes"][0]["evidence_sha256"]
    evidence[digest] = b"x" * 65537
    assert not _check(plan, envelopes, inventory, evidence)["eligible"]
    assert not _check(plan, envelopes * 257, inventory, evidence)["eligible"]


def test_duplicate_json_keys_and_numeric_boolean_masquerade_fail_closed():
    plan, envelopes, inventory, evidence = _fixture()
    old_digest = envelopes[0]["nodes"][0]["evidence_sha256"]
    proof = json.loads(evidence.pop(old_digest))
    proof["digest_verified"] = 1
    raw = _canonical(proof)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    evidence[digest] = raw
    envelopes[0]["nodes"][0]["evidence_sha256"] = digest
    envelopes[0]["mac"] = hmac.new(
        SECRET, canonical_attestation_payload(envelopes[0]), hashlib.sha256
    ).hexdigest()
    assert not _check(plan, envelopes, inventory, evidence)["eligible"]

    proof["digest_verified"] = True
    raw = _canonical(proof).replace(b'"node_id":', b'"node_id":"worker-other","node_id":')
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    evidence[digest] = raw
    envelopes[0]["nodes"][0]["evidence_sha256"] = digest
    envelopes[0]["mac"] = hmac.new(
        SECRET, canonical_attestation_payload(envelopes[0]), hashlib.sha256
    ).hexdigest()
    assert not _check(plan, envelopes, inventory, evidence)["eligible"]


def test_malformed_plan_identity_fails_closed_without_exception():
    plan, envelopes, inventory, evidence = _fixture()
    plan["items"][0]["cluster_ref"] = ["arena"]
    report = _check(plan, envelopes, inventory, evidence)
    assert report["status"] == "RED"
    assert any("planned clusters" in failure for failure in report["failures"])


def test_evidence_store_failure_is_red_and_does_not_expose_provider_details():
    plan, envelopes, inventory, _ = _fixture()

    class StoreFailure(Exception):
        pass

    class FailedStore(dict):
        def __getitem__(self, key):
            raise StoreFailure("token=private-provider-detail")

    report = _check(plan, envelopes, inventory, FailedStore())

    assert report["status"] == "RED"
    assert "private-provider-detail" not in str(report)
