from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.services.artifact_prepull import (
    build_event_prepull_plan,
    evaluate_prepull_receipts,
)
from app.services.catalog_supply_chain import build_supply_chain_report

ROOT = Path(__file__).parents[2]


def _report() -> dict:
    return build_supply_chain_report(
        ROOT / "config/catalog-artifact-policy.yaml",
        ROOT,
    )


def _assignments() -> list[dict]:
    return [
        {
            "workshop_id": "serve-wave-1",
            "catalog_id": "intel-llm-cpu-serving",
            "cluster_ref": "arena",
        },
        {
            "workshop_id": "serve-wave-2",
            "catalog_id": "intel-llm-cpu-serving",
            "cluster_ref": "arena",
        },
        {
            "workshop_id": "agent-wave-1",
            "catalog_id": "intel-xeon6-agent-201",
            "cluster_ref": "brutus",
        },
    ]


def _plan() -> dict:
    return build_event_prepull_plan(
        event_id="event-1",
        starts_at=datetime(2026, 10, 1, 14, 0, tzinfo=UTC),
        assignments=_assignments(),
        artifact_report=_report(),
    )


def _receipts(plan: dict) -> list[dict]:
    return [
        {
            "schema_version": "launchpad.redhat.com/event-artifact-prepull-receipt/v1",
            "plan_id": plan["plan_id"],
            "cluster_ref": item["cluster_ref"],
            "image": item["image"],
            "status": "passed",
            "cache_state": "present",
            "digest_verified": True,
            "signature_verified": True,
            "mirror_source": "quay.io/redhat-gpte",
            "nodes_expected": 2,
            "nodes_ready": 2,
            "observed_at": "2026-09-30T15:00:00+00:00",
            "evidence": ["evidence/prepull.json"],
        }
        for item in plan["items"]
    ]


def test_event_prepull_plan_is_deterministic_and_deduplicates_images() -> None:
    first = _plan()
    second = _plan()

    assert first == second
    assert first["plan_id"].startswith("sha256:")
    assert len(first["items"]) == 4
    arena = [item for item in first["items"] if item["cluster_ref"] == "arena"]
    assert arena[0]["workshop_ids"] == ["serve-wave-1", "serve-wave-2"]
    assert all("@sha256:" in item["image"] for item in first["items"])


def test_event_prepull_plan_rejects_unscheduled_or_mutable_inputs() -> None:
    with pytest.raises(ValueError, match="timezone"):
        build_event_prepull_plan(
            event_id="event-1",
            starts_at=datetime.fromisoformat("2026-10-01T14:00:00"),
            assignments=_assignments(),
            artifact_report=_report(),
        )

    report = deepcopy(_report())
    report["catalogs"]["intel-llm-cpu-serving"]["images"] = ["example/image:latest"]
    with pytest.raises(ValueError, match="not immutable"):
        build_event_prepull_plan(
            event_id="event-1",
            starts_at=datetime(2026, 10, 1, 14, 0, tzinfo=UTC),
            assignments=_assignments(),
            artifact_report=report,
        )


def test_complete_receipts_make_plan_integration_eligible() -> None:
    plan = _plan()

    report = evaluate_prepull_receipts(plan, _receipts(plan))

    assert report["status"] == "GREEN-integration"
    assert report["eligible"] is True
    assert report["planned_items"] == report["proven_items"] == 4


def test_missing_incomplete_or_wrong_plan_receipts_fail_closed() -> None:
    plan = _plan()
    receipts = _receipts(plan)
    receipts.pop()
    receipts[0]["nodes_ready"] = 1
    receipts[1]["plan_id"] = "sha256:" + "f" * 64

    report = evaluate_prepull_receipts(plan, receipts)

    assert report["status"] == "RED"
    assert report["eligible"] is False
    assert any("node coverage is incomplete" in item for item in report["failures"])
    assert any("plan_id does not match" in item for item in report["failures"])
    assert sum("receipt is missing" in item for item in report["failures"]) == 2


@pytest.mark.parametrize(
    "observed_at",
    [
        None,
        "2026-09-30T13:29:59+00:00",  # Earlier than the planned warm-up window.
        "2026-10-01T13:30:01+00:00",  # Too late for the event margin.
        "2026-09-30T15:00:00",  # A naive timestamp cannot prove the window.
        "not-a-timestamp",
    ],
)
def test_receipt_without_timely_timezone_aware_observation_fails_closed(
    observed_at: str | None,
) -> None:
    plan = _plan()
    receipts = _receipts(plan)
    receipts[0]["observed_at"] = observed_at

    report = evaluate_prepull_receipts(plan, receipts)

    assert report["eligible"] is False
    assert any("observation time" in failure for failure in report["failures"])
