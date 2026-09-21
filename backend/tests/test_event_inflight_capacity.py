"""Proof that observed resource pressure cannot be double-counted or ignored."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from app.domain.event_inflight_capacity import (
    EventInflightCapacitySnapshot,
    InflightClusterUsage,
    InflightResourceVector,
    InflightWorkloadUsage,
)
from app.domain.events import EventCapacityReservation, EventResourceVector
from app.services.event_inflight_capacity import assess_event_inflight_capacity

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)
SNAPSHOT_ID = "sha256:" + "a" * 64


def _resources(*, cpu=0, memory=0, pods=0, model_slots=0):
    return InflightResourceVector(
        cpu_millicores=cpu, memory_mib=memory, pods=pods, model_slots=model_slots
    )


def _reservation(*, reservation_id="event:cohort:lab", status="consumed", cluster="arena"):
    fields = {
        "reservation_id": reservation_id,
        "event_id": "event",
        "cohort_id": "cohort",
        "lab_ref": "lab",
        "catalog_id": "catalog",
        "catalog_release": "v1",
        "cluster_ref": cluster,
        "matrix_id": "matrix",
        "matrix_digest": "digest",
        "fleet_snapshot_id": "fleet",
        "resources": EventResourceVector(
            seats=2, cpu_millicores=2000, memory_mib=2048, pods=4, model_slots=2
        ),
        "expires_at": NOW + timedelta(hours=4),
        "created_at": NOW - timedelta(minutes=1),
        "status": status,
    }
    if status == "consumed":
        fields.update(workshop_id="workshop", consumed_at=NOW - timedelta(seconds=30))
    return EventCapacityReservation(**fields)


def _workload(**changes):
    fields = {
        "namespace": "seat-one",
        "reservation_id": "event:cohort:lab",
        "workshop_id": "workshop",
        "seat_refs": ["seat-1"],
        "resources": _resources(cpu=1000, memory=1024, pods=2, model_slots=1),
    }
    fields.update(changes)
    return InflightWorkloadUsage(**fields)


def _snapshot(*, workloads=None, observed_at=NOW, complete=True, cluster="arena"):
    return EventInflightCapacitySnapshot(
        snapshot_id=SNAPSHOT_ID,
        observed_at=observed_at,
        clusters=[
            InflightClusterUsage(
                cluster_id=cluster,
                allocatable=_resources(cpu=6000, memory=8192, pods=10, model_slots=4),
                accounting_complete=complete,
                workloads=workloads if workloads is not None else [_workload()],
            )
        ],
    )


def test_missing_stale_future_or_incomplete_evidence_blocks():
    candidate = {"arena": _resources(cpu=1000, pods=1)}
    active = [_reservation()]
    for snapshot, reason in [
        (None, "unavailable"),
        (_snapshot(observed_at=NOW - timedelta(seconds=121)), "stale"),
        (_snapshot(observed_at=NOW + timedelta(seconds=31)), "future"),
        (_snapshot(complete=False), "incomplete"),
        (_snapshot(cluster="brutus"), "arena"),
    ]:
        result = assess_event_inflight_capacity(candidate, active, snapshot, now=NOW)
        assert result.status == "blocked"
        assert reason in result.explanation


def test_consumed_usage_is_counted_once_and_unused_hold_stays_reserved():
    # 6 CPU allocatable - 1 CPU observed use - 1 CPU unconsumed reservation = 4.
    # Subtracting the entire 2 CPU reservation after observed use would yield 3.
    result = assess_event_inflight_capacity(
        {"arena": _resources(cpu=4000, memory=6144, pods=6, model_slots=2)},
        [_reservation()],
        _snapshot(),
        now=NOW,
    )
    assert result.status == "available"
    assert result.headroom["arena"] == _resources(cpu=4000, memory=6144, pods=6, model_slots=2)


def test_external_usage_reduces_physical_headroom_and_model_pressure_blocks():
    external = InflightWorkloadUsage(
        namespace="other-team", resources=_resources(cpu=1000, pods=1, model_slots=1)
    )
    result = assess_event_inflight_capacity(
        {"arena": _resources(cpu=4000, pods=6, model_slots=2)},
        [_reservation()],
        _snapshot(workloads=[_workload(), external]),
        now=NOW,
    )
    assert result.status == "blocked"
    assert "cpu_millicores" in result.explanation
    assert "model_slots" in result.explanation
    assert result.headroom["arena"].model_slots == 1


def test_held_reservation_without_usage_reduces_free_headroom():
    result = assess_event_inflight_capacity(
        {"arena": _resources(cpu=4000)},
        [_reservation(status="held")],
        _snapshot(workloads=[]),
        now=NOW,
    )
    assert result.status == "available"
    assert result.headroom["arena"].cpu_millicores == 4000


@pytest.mark.parametrize(
    "workloads,reason",
    [
        ([_workload(reservation_id="unknown")], "unknown reservation"),
        ([_workload(workshop_id="other")], "workshop"),
        ([_workload(seat_refs=["seat-1", "seat-1"])], "duplicate seat"),
        ([_workload(seat_refs=["s1", "s2", "s3"])], "seat limit"),
        ([_workload(resources=_resources(cpu=3000))], "exceeds reservation"),
        (
            [
                _workload(),
                InflightWorkloadUsage(namespace="seat-one", resources=_resources(pods=1)),
            ],
            "ambiguous namespace",
        ),
    ],
)
def test_ambiguous_or_drifting_ownership_blocks(workloads, reason):
    result = assess_event_inflight_capacity(
        {"arena": _resources(cpu=1)},
        [_reservation()],
        _snapshot(workloads=workloads),
        now=NOW,
    )
    assert result.status == "blocked"
    assert reason in result.explanation


def test_cross_cluster_reservation_and_negative_physical_free_block():
    wrong_cluster = assess_event_inflight_capacity(
        {"arena": _resources(cpu=1)},
        [_reservation(cluster="brutus")],
        _snapshot(),
        now=NOW,
    )
    assert wrong_cluster.status == "blocked"
    assert "cluster" in wrong_cluster.explanation
    negative = assess_event_inflight_capacity(
        {"arena": _resources(cpu=1)},
        [],
        _snapshot(
            workloads=[InflightWorkloadUsage(namespace="external", resources=_resources(cpu=7000))]
        ),
        now=NOW,
    )
    assert negative.status == "blocked"
    assert "allocatable" in negative.explanation


def test_snapshot_rejects_duplicate_cluster_and_naive_timestamps():
    cluster = _snapshot().clusters[0]
    with pytest.raises(ValueError, match="duplicate cluster"):
        EventInflightCapacitySnapshot(
            snapshot_id=SNAPSHOT_ID, observed_at=NOW, clusters=[cluster, cluster]
        )
    with pytest.raises(ValueError, match="timezone"):
        _snapshot(observed_at=NOW.replace(tzinfo=None))


def test_producer_contract_matches_runtime_dimensions():
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts/event-inflight-capacity-v1.yaml").read_text()
    )
    assert contract["schema_version"] == "1.0"
    assert set(contract["resource_dimensions"]) == set(InflightResourceVector.model_fields)
    assert set(contract["cluster_row_required"]) == set(InflightClusterUsage.model_fields)
