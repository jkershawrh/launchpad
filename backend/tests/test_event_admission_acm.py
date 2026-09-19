from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.domain.acm import AcmClusterObservation, AcmPlacementSnapshot
from app.domain.events import EventCapacitySupply, EventClusterCapacity
from app.services.event_admission import (
    EventAdmissionUnavailableError,
    apply_acm_eligibility,
)

NOW = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)


def _snapshot(*, observed_at: datetime = NOW) -> AcmPlacementSnapshot:
    return AcmPlacementSnapshot(
        namespace="launchpad-fleet",
        placement_name="launchpad-events",
        snapshot_id="sha256:" + "b" * 64,
        observed_at=observed_at,
        clusters=[
            AcmClusterObservation(
                cluster_id="arena",
                available=True,
                hub_accepted=True,
                acm_eligible=True,
            ),
            AcmClusterObservation(
                cluster_id="brutus",
                available=False,
                hub_accepted=True,
                acm_eligible=False,
                reasons=["ManagedClusterConditionAvailable is not True"],
            ),
        ],
    )


def _supply() -> EventCapacitySupply:
    return EventCapacitySupply(
        matrix_id="matrix-v1",
        matrix_digest="sha256:" + "a" * 64,
        clusters=[
            EventClusterCapacity(cluster_id="arena", enabled=True, certified_seats=30),
            EventClusterCapacity(cluster_id="brutus", enabled=True, certified_seats=30),
            EventClusterCapacity(
                cluster_id="flightpath",
                enabled=False,
                certified_seats=0,
                dr_reserved_seats=30,
            ),
        ],
    )


def test_acm_candidates_intersect_matrix_without_mutating_certification():
    source = _supply()

    filtered = apply_acm_eligibility(source, _snapshot(), now=NOW)

    assert [item.enabled for item in source.clusters] == [True, True, False]
    assert [item.enabled for item in filtered.clusters] == [True, False, False]
    assert filtered.clusters[2].dr_reserved_seats == 30
    assert filtered.matrix_id == "matrix-v1"
    assert filtered.matrix_digest == "sha256:" + "a" * 64
    assert filtered.fleet_snapshot_id == "sha256:" + "b" * 64
    assert filtered.fleet_observed_at == NOW


def test_stale_acm_snapshot_fails_closed():
    with pytest.raises(EventAdmissionUnavailableError, match="stale by 1 second"):
        apply_acm_eligibility(
            _supply(),
            _snapshot(observed_at=NOW - timedelta(seconds=121)),
            now=NOW,
            max_age_seconds=120,
        )


def test_future_acm_snapshot_fails_closed():
    with pytest.raises(EventAdmissionUnavailableError, match="future-dated"):
        apply_acm_eligibility(
            _supply(),
            _snapshot(observed_at=NOW + timedelta(seconds=31)),
            now=NOW,
            max_future_skew_seconds=30,
        )


def test_empty_acm_candidate_set_disables_all_normal_capacity():
    snapshot = _snapshot()
    snapshot.clusters = []

    filtered = apply_acm_eligibility(_supply(), snapshot, now=NOW)

    assert not any(item.enabled for item in filtered.clusters)
    assert sum(item.dr_reserved_seats for item in filtered.clusters) == 30
