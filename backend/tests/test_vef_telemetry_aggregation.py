from copy import deepcopy

import pytest
from app.services.vef_telemetry_aggregation import aggregate_vef_receipts


def _receipts() -> list[dict]:
    base = {"schema_version": "launchpad.vef-aggregate-receipt.v1", "pilot_id": "pilot-1"}
    return [
        {
            **base,
            "receipt_id": "sha256:" + "a" * 64,
            "kind": "track_outcome",
            "data": {
                "track_id": "serve-llms",
                "provisioned_seats": 30,
                "activated_journeys": 28,
                "successful_journeys": 25,
                "failed_journeys": 2,
                "unknown_outcomes": 1,
                "evidence_state": "authoritative",
            },
        },
        {
            **base,
            "receipt_id": "sha256:" + "b" * 64,
            "kind": "platform_lifecycle",
            "data": {
                "measurement_state": "authoritative",
                "orders_requested": 1,
                "seats_requested": 30,
                "seats_ready": 30,
                "seats_reclaimed": 30,
                "provisioning_p95_seconds": 92.5,
                "reclaim_p95_seconds": 61.0,
                "human_interventions": 1,
                "residue_count": 0,
            },
        },
        {
            **base,
            "receipt_id": "sha256:" + "c" * 64,
            "kind": "ai_usage",
            "data": {
                "measurement_state": "authoritative",
                "actual_requests": 400,
                "input_tokens": 12000,
                "output_tokens": 6000,
                "inference_cost_usd": 18.25,
            },
        },
        {
            **base,
            "receipt_id": "sha256:" + "d" * 64,
            "kind": "cost_allocation",
            "data": {
                "measurement_state": "authoritative",
                "allocation_basis": "successful_journey",
                "shared_platform_cost_usd": 100.0,
                "delivery_cost_usd": 200.0,
                "allocated_inference_cost_usd": 18.25,
                "unallocated_cost_usd": 0.0,
                "cost_center_ready": True,
                "chargeback_ready": True,
            },
        },
    ]


def test_receipts_build_deterministic_vef_analytics_input() -> None:
    report = aggregate_vef_receipts(_receipts())
    assert report["status"] == "ready"
    assert report["ai_usage"]["actual_requests"] == 400
    assert report["analytics"]["track_outcomes"][0]["successful_journeys"] == 25
    assert report["analytics"]["platform_lifecycle"]["residue_count"] == 0
    assert report["analytics"]["cost_allocation"]["unallocated_cost_usd"] == 0.0
    assert report["evidence_sources"] == ["sha256:" + char * 64 for char in "abcd"]


def test_missing_or_duplicate_receipts_fail_closed() -> None:
    receipts = _receipts()[:-1]
    with pytest.raises(ValueError, match="required receipt"):
        aggregate_vef_receipts(receipts)
    receipts = _receipts()
    receipts.append(deepcopy(receipts[0]))
    with pytest.raises(ValueError, match="duplicate receipt"):
        aggregate_vef_receipts(receipts)


def test_track_counts_must_reconcile() -> None:
    receipts = _receipts()
    receipts[0]["data"]["unknown_outcomes"] = 0
    with pytest.raises(ValueError, match="track outcome counts"):
        aggregate_vef_receipts(receipts)


@pytest.mark.parametrize(
    "key", ["email", "prompt", "response", "participant_id", "namespace", "credential"]
)
def test_sensitive_fields_are_rejected_at_ingestion(key: str) -> None:
    receipts = _receipts()
    receipts[0]["data"][key] = "must-not-enter-vef"
    with pytest.raises(ValueError, match="sensitive field"):
        aggregate_vef_receipts(receipts)


def test_authoritative_measurement_cannot_hide_unknown_values() -> None:
    receipts = _receipts()
    receipts[2]["data"]["input_tokens"] = None
    with pytest.raises(ValueError, match="authoritative receipt"):
        aggregate_vef_receipts(receipts)


def test_unversioned_extra_metrics_are_rejected() -> None:
    receipts = _receipts()
    receipts[2]["data"]["estimated_tokens"] = 999
    with pytest.raises(ValueError, match="data fields"):
        aggregate_vef_receipts(receipts)
