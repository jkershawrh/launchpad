"""Local model-slot evidence tests; no network or cluster access."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.clusters import ClusterTarget
from app.services.event_inflight_capacity_collector import InflightCollectionBlocked
from app.services.event_model_slot_source import FileModelSlotSource

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)
ARENA = ClusterTarget(cluster_id="arena", display_name="Arena", ingress_domain="apps.arena.test")
BRUTUS = ClusterTarget(
    cluster_id="brutus", display_name="Brutus", ingress_domain="apps.brutus.test"
)


def document(**changes):
    return {
        "schema_version": "1.0",
        "cluster_id": "arena",
        "observed_at": NOW.isoformat(),
        "basis": "promoted-model-concurrency",
        "capacity_policy_ref": "release-2026-09-21/arena",
        "allocatable_slots": 0,
        "complete": True,
        **changes,
    }


def source(tmp_path, payload):
    path = tmp_path / "slots.json"
    path.write_text(json.dumps(payload))
    return FileModelSlotSource(path, clock=lambda: NOW)


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
    missing = FileModelSlotSource(tmp_path / "missing.json", clock=lambda: NOW)
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        missing.observe_model_slots(ARENA)
    path = tmp_path / "duplicate.json"
    path.write_text(
        json.dumps(document()).replace(
            '"allocatable_slots": 0', '"allocatable_slots": 0, "allocatable_slots": 25'
        )
    )
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        FileModelSlotSource(path, clock=lambda: NOW).observe_model_slots(ARENA)


def test_symlink_and_extra_field_block(tmp_path):
    target = tmp_path / "target.json"
    target.write_text(json.dumps(document()))
    link = tmp_path / "slots.json"
    link.symlink_to(target)
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        FileModelSlotSource(link, clock=lambda: NOW).observe_model_slots(ARENA)
    with pytest.raises(InflightCollectionBlocked, match="model slot"):
        source(tmp_path, document(ready_replicas=4)).observe_model_slots(ARENA)
