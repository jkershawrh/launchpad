from __future__ import annotations

from copy import deepcopy

import pytest
from app.domain.capacity_reconciliation import (
    CapacityMeasurement,
    RecordedEventManifest,
    RecordedPilotPostmortem,
)
from app.services.event_capacity_reconciliation import reconcile_capacity


def _manifest() -> dict:
    return {
        "api_version": "launchpad.intel.com/v1",
        "kind": "EventManifest",
        "spec": {
            "event_id": "event-1",
            "name": "Recorded event",
            "owner": "owner",
            "technical_approver": "approver",
            "exposure_policy": "public_code",
            "placement_policy": "single_cluster_per_workshop",
            "cohorts": [{"cohort_id": "wave-1", "participants": 5, "lab_refs": ["lab-a"]}],
            "labs": [
                {
                    "lab_ref": "lab-a",
                    "catalog_id": "catalog-a",
                    "catalog_release": "release-a",
                }
            ],
            "retention": {"hours": 8, "starts_from": "cohort_start"},
            "approval": {
                "event_owner_approved": True,
                "technical_approver_approved": True,
                "approved_seat_environments": 5,
                "approved_retention_hours": 8,
            },
        },
    }


def _postmortem() -> dict:
    return {
        "schema_version": 1,
        "snapshot_at": "2026-09-17T21:56:00Z",
        "event": "Recorded event",
        "summary": {
            "waves": 1,
            "workshops_ordered": 1,
            "workshops_ready_retained": 1,
            "workshops_reclaimed": 0,
            "seats_provisioned": 5,
            "seats_claimed": 4,
            "seats_unclaimed": 1,
            "claim_utilization_percent": 80.0,
        },
        "catalogs": [
            {
                "name": "Recorded catalog label",
                "ordered": 5,
                "claimed": 4,
                "unclaimed": 1,
                "claim_percent": 80.0,
            }
        ],
        "waves": [{"wave": 1, "ordered": 5, "claimed": 4, "unclaimed": 1, "claim_percent": 80.0}],
        "workshops": [
            {
                "wave": 1,
                "catalog": "Recorded catalog label",
                "cluster": "Arena",
                "workshop": "abc123",
                "claimed": 4,
                "ordered": 5,
                "state": "ready / retained",
                "expires": "2026-09-18T00:00:00Z",
            }
        ],
        "clusters": [
            {
                "name": "Arena",
                "seats": 5,
                "claimed": 4,
                "pods_ready": 10,
                "pods_total": 10,
                "routes_admitted": 12,
                "routes_total": 12,
                "restarts": 0,
                "note": "Recorded snapshot.",
            }
        ],
        "models": [{"name": "Model A", "ready": 1, "desired": 1}],
        "telemetry": [],
    }


def test_unavailable_measurement_cannot_carry_a_zero_or_omit_reason():
    with pytest.raises(ValueError, match="must not carry a value"):
        CapacityMeasurement(status="unavailable", value=0, reason="not measured")
    with pytest.raises(ValueError, match="requires a reason"):
        CapacityMeasurement(status="unavailable", value=None, reason=None)


def test_reconciliation_preserves_observed_counts_and_marks_actual_usage_unavailable():
    result = reconcile_capacity(
        RecordedEventManifest.model_validate(_manifest()),
        RecordedPilotPostmortem.model_validate(_postmortem()),
        manifest_source="fixtures/events/test.yaml",
        manifest_digest="sha256:" + "a" * 64,
        postmortem_source="docs/test-postmortem.json",
        postmortem_digest="sha256:" + "b" * 64,
    )

    assert result.schema_version == "launchpad.intel.com/capacity-reconciliation/v1"
    assert result.event_id == "event-1"
    assert result.forecast.seat_environments == 5
    assert result.observed.seats_provisioned == 5
    assert result.observed.seats_claimed == 4
    assert result.observed.workshops_reclaimed == 0
    assert result.variance.provisioned_seat_environments == 0
    assert result.variance.unclaimed_seat_environments == 1
    assert result.observed.reservations.status == "unavailable"
    assert result.observed.reservations.value is None
    for name in (
        "actual_cpu_millicore_hours",
        "actual_memory_mib_hours",
        "actual_storage_gib_hours",
        "model_requests",
        "model_input_tokens",
        "model_output_tokens",
        "model_queue_seconds",
        "image_cache_hit_rate",
    ):
        measurement = getattr(result.observed, name)
        assert measurement.status == "unavailable"
        assert measurement.value is None
        assert measurement.reason


def test_observed_catalog_label_is_not_guessed_into_a_catalog_id():
    result = reconcile_capacity(
        RecordedEventManifest.model_validate(_manifest()),
        RecordedPilotPostmortem.model_validate(_postmortem()),
        manifest_source="fixture.yaml",
        manifest_digest="sha256:" + "a" * 64,
        postmortem_source="postmortem.json",
        postmortem_digest="sha256:" + "b" * 64,
    )

    observed_catalog = result.observed.catalogs[0]
    assert observed_catalog.catalog_label == "Recorded catalog label"
    assert observed_catalog.catalog_id.status == "unavailable"
    assert observed_catalog.catalog_id.value is None


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["summary"].update(seats_claimed=6),
        lambda payload: payload["summary"].update(seats_unclaimed=0),
        lambda payload: payload["summary"].update(workshops_ordered=2),
    ],
)
def test_inconsistent_recorded_postmortem_fails_closed(mutation):
    payload = deepcopy(_postmortem())
    mutation(payload)

    with pytest.raises(ValueError, match="recorded postmortem"):
        RecordedPilotPostmortem.model_validate(payload)
