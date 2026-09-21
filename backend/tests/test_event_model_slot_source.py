"""Local model-slot evidence tests; no network or cluster access."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.clusters import ClusterTarget
from app.services.event_inflight_capacity_collector import InflightCollectionBlocked
from app.services.event_model_slot_policy import PinnedModelConcurrencyPolicy
from app.services.event_model_slot_source import FileModelSlotSource

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)
ARENA = ClusterTarget(cluster_id="arena", display_name="Arena", ingress_domain="apps.arena.test")
BRUTUS = ClusterTarget(
    cluster_id="brutus", display_name="Brutus", ingress_domain="apps.brutus.test"
)


def document(**changes):
    return {
        "schema_version": "1.1",
        "cluster_id": "arena",
        "observed_at": NOW.isoformat(),
        "basis": "promoted-model-concurrency",
        "capacity_policy_ref": "release-2026-09-21/arena",
        "capacity_policy_digest": "",
        "model_id": "granite-8b",
        "model_release": "granite-8b-v1",
        "allocatable_slots": 0,
        "complete": True,
        **changes,
    }


def policy_document(**changes):
    return {
        "schema_version": "1.0",
        "policy_id": "release-2026-09-21/arena",
        "cluster_id": "arena",
        "model_id": "granite-8b",
        "model_release": "granite-8b-v1",
        "max_concurrent_requests": 25,
        "promotion_state": "promoted",
        "approved_at": NOW.isoformat(),
        "approvers": ["model-owner", "capacity-reviewer"],
        **changes,
    }


def authority(tmp_path, *, payload=None, trusted_digest=None):
    path = tmp_path / "policy.json"
    source = json.dumps(payload if payload is not None else policy_document()).encode()
    path.write_bytes(source)
    digest = "sha256:" + hashlib.sha256(source).hexdigest()
    return PinnedModelConcurrencyPolicy(path, trusted_digest=trusted_digest or digest)


def source(tmp_path, payload, *, policy_authority=None):
    policy_authority = policy_authority or authority(tmp_path)
    path = tmp_path / "slots.json"
    evidence = dict(payload)
    if evidence.get("capacity_policy_digest") == "":
        evidence["capacity_policy_digest"] = policy_authority.trusted_digest
    path.write_text(json.dumps(evidence))
    return FileModelSlotSource(path, policy_authority=policy_authority, clock=lambda: NOW)


def test_explicit_zero_is_complete_evidence(tmp_path):
    slots = source(tmp_path, document()).observe_model_slots(ARENA)
    assert slots.cluster_id == "arena"
    assert slots.allocatable_slots == 0
    assert slots.complete is True
    assert slots.observed_at == NOW


def test_positive_capacity_is_not_inferred_from_replicas(tmp_path):
    slots = source(tmp_path, document(allocatable_slots=25)).observe_model_slots(ARENA)
    assert slots.allocatable_slots == 25


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"complete": None},
        {"allocatable_slots": None},
        {"allocatable_slots": False},
        {"allocatable_slots": -1},
        {"allocatable_slots": 2.5},
        {"capacity_policy_ref": ""},
        {"capacity_policy_ref": "arbitrary"},
        {"model_id": "different-model"},
        {"model_release": "different-release"},
        {"allocatable_slots": 26},
        {"basis": "ready-replicas"},
        {"schema_version": "2.0"},
        {"observed_at": "2026-09-21T12:00:00"},
        {"observed_at": (NOW - timedelta(seconds=121)).isoformat()},
        {"observed_at": (NOW + timedelta(seconds=31)).isoformat()},
    ],
)
def test_partial_or_untrusted_evidence_blocks(tmp_path, change):
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(tmp_path, document(**change)).observe_model_slots(ARENA)


def test_missing_capacity_field_is_not_zero(tmp_path):
    payload = document()
    del payload["allocatable_slots"]
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(tmp_path, payload).observe_model_slots(ARENA)


def test_wrong_cluster_never_falls_back(tmp_path):
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(tmp_path, document()).observe_model_slots(BRUTUS)


def test_unavailable_file_and_duplicate_keys_block(tmp_path):
    pinned = authority(tmp_path)
    missing = FileModelSlotSource(
        tmp_path / "missing.json", policy_authority=pinned, clock=lambda: NOW
    )
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        missing.observe_model_slots(ARENA)
    path = tmp_path / "duplicate.json"
    path.write_text(
        json.dumps(document()).replace(
            '"allocatable_slots": 0', '"allocatable_slots": 0, "allocatable_slots": 25'
        )
    )
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        FileModelSlotSource(path, policy_authority=pinned, clock=lambda: NOW).observe_model_slots(
            ARENA
        )


def test_symlink_and_extra_field_block(tmp_path):
    target = tmp_path / "target.json"
    target.write_text(json.dumps(document()))
    link = tmp_path / "slots.json"
    link.symlink_to(target)
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        FileModelSlotSource(
            link, policy_authority=authority(tmp_path), clock=lambda: NOW
        ).observe_model_slots(ARENA)
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(tmp_path, document(ready_replicas=4)).observe_model_slots(ARENA)


def test_unpinned_policy_is_not_an_available_source(tmp_path):
    with pytest.raises(TypeError, match="policy_authority"):
        FileModelSlotSource(tmp_path / "slots.json", clock=lambda: NOW)
    with pytest.raises(TypeError, match="policy_authority"):
        FileModelSlotSource(tmp_path / "slots.json", policy_authority=None, clock=lambda: NOW)


@pytest.mark.parametrize(
    "change",
    [
        {"max_concurrent_requests": 0},
        {"cluster_id": "brutus"},
        {"model_id": "other"},
        {"model_release": "other"},
        {"promotion_state": "draft"},
        {"approvers": ["same", "same"]},
        {"approved_at": "2026-09-21T12:00:00"},
    ],
)
def test_unapproved_or_mismatched_policy_blocks(tmp_path, change):
    pinned = authority(tmp_path, payload=policy_document(**change))
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(
            tmp_path, document(allocatable_slots=1), policy_authority=pinned
        ).observe_model_slots(ARENA)


def test_policy_file_cannot_change_after_trusted_digest_is_pinned(tmp_path):
    pinned = authority(tmp_path)
    pinned.path.write_text(json.dumps(policy_document(max_concurrent_requests=100)))
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(
            tmp_path, document(allocatable_slots=25), policy_authority=pinned
        ).observe_model_slots(ARENA)


def test_self_declared_digest_cannot_replace_trust_anchor(tmp_path):
    pinned = authority(tmp_path)
    mismatch = "sha256:" + "0" * 64
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(
            tmp_path,
            document(capacity_policy_digest=mismatch),
            policy_authority=pinned,
        ).observe_model_slots(ARENA)


def test_legacy_self_declared_evidence_blocks(tmp_path):
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(tmp_path, document(schema_version="1.0")).observe_model_slots(ARENA)


def test_observation_must_follow_independently_approved_policy(tmp_path):
    pinned = authority(
        tmp_path,
        payload=policy_document(approved_at=(NOW + timedelta(seconds=1)).isoformat()),
    )
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(tmp_path, document(), policy_authority=pinned).observe_model_slots(ARENA)


def test_anchor_rejects_bad_digest_and_duplicate_policy_keys(tmp_path):
    with pytest.raises(ValueError, match="trusted policy digest"):
        PinnedModelConcurrencyPolicy(tmp_path / "policy.json", trusted_digest="not-a-digest")
    pinned = authority(tmp_path)
    source_bytes = pinned.path.read_bytes().replace(
        b'"max_concurrent_requests": 25',
        b'"max_concurrent_requests": 25, "max_concurrent_requests": 100',
    )
    pinned.path.write_bytes(source_bytes)
    duplicate_digest = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    duplicate_anchor = PinnedModelConcurrencyPolicy(pinned.path, trusted_digest=duplicate_digest)
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(
            tmp_path, document(allocatable_slots=1), policy_authority=duplicate_anchor
        ).observe_model_slots(ARENA)
