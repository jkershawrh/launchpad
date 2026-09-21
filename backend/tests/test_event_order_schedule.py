"""Local contract proof for pre-approved, serial event ordering windows."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from app.domain.events import EventManifest
from app.services.event_order_schedule import (
    EventOrderSchedule,
    evaluate_event_order_schedule,
    manifest_scope_digest,
)

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "fixtures/events/september-17-2026.yaml"
CONTRACT = ROOT / "contracts/event-order-schedule-v1.yaml"


def _manifest() -> EventManifest:
    payload = yaml.safe_load(PILOT.read_text())["spec"]
    for index, cohort in enumerate(payload["cohorts"]):
        cohort["starts_at"] = (
            datetime(2026, 10, 1, 14, tzinfo=UTC) + timedelta(hours=3 * index)
        ).isoformat()
    return EventManifest.model_validate(payload)


def _schedule(manifest: EventManifest) -> dict:
    windows = []
    for cohort in manifest.cohorts:
        assert cohort.starts_at is not None
        for index, lab_ref in enumerate(cohort.lab_refs):
            begins = cohort.starts_at - timedelta(minutes=30 - 5 * index)
            windows.append(
                {
                    "cohort_id": cohort.cohort_id,
                    "lab_ref": lab_ref,
                    "not_before": begins.isoformat(),
                    "not_after": (begins + timedelta(minutes=5)).isoformat(),
                }
            )
    return {
        "schema_version": "launchpad.intel.com/event-order-schedule/v1",
        "event_id": manifest.event_id,
        "manifest_digest": manifest_scope_digest(manifest),
        "policy": "serial_per_event",
        "approved_by": [manifest.owner, manifest.technical_approver],
        "approved_at": "2026-09-30T12:00:00Z",
        "windows": windows,
    }


def test_complete_schedule_binds_every_workshop_to_approved_manifest():
    manifest = _manifest()
    result = evaluate_event_order_schedule(
        manifest, EventOrderSchedule.model_validate(_schedule(manifest))
    )

    assert result.eligible is True
    assert result.status == "GREEN-local"
    assert result.workshop_count == 9
    assert result.seat_environments == 270


def test_schedule_contract_requires_approval_and_exact_windows():
    schemas = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"]
    schedule = schemas["EventOrderSchedule"]

    assert {"manifest_digest", "approved_by", "approved_at", "windows"} <= set(
        schedule["required"]
    )
    assert schedule["properties"]["policy"]["const"] == "serial_per_event"


def test_schedule_cli_emits_machine_readable_local_gate(tmp_path: Path):
    manifest = _manifest()
    manifest_path = tmp_path / "event.yaml"
    schedule_path = tmp_path / "schedule.yaml"
    output_path = tmp_path / "decision.json"
    manifest_path.write_text(yaml.safe_dump(manifest.model_dump(mode="json")))
    schedule_path.write_text(yaml.safe_dump(_schedule(manifest)))

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validate_event_order_schedule.py"),
            "--manifest",
            str(manifest_path),
            "--schedule",
            str(schedule_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output_path.read_text())["status"] == "GREEN-local"

    rejected = _schedule(manifest)
    rejected["windows"].pop()
    schedule_path.write_text(yaml.safe_dump(rejected))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validate_event_order_schedule.py"),
            "--manifest",
            str(manifest_path),
            "--schedule",
            str(schedule_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(output_path.read_text())["status"] == "RED"


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "overlap"])
def test_schedule_rejects_incomplete_or_overlapping_workshop_windows(change: str):
    manifest = _manifest()
    payload = _schedule(manifest)
    if change == "missing":
        payload["windows"].pop()
    elif change == "duplicate":
        payload["windows"].append(deepcopy(payload["windows"][0]))
    elif change == "extra":
        payload["windows"][0]["lab_ref"] = "unapproved-lab"
    else:
        payload["windows"][1]["not_before"] = payload["windows"][0]["not_before"]

    result = evaluate_event_order_schedule(
        manifest, EventOrderSchedule.model_validate(payload)
    )

    assert result.eligible is False
    assert result.status == "RED"


def test_schedule_rejects_changed_catalog_even_when_seat_count_is_identical():
    manifest = _manifest()
    payload = _schedule(manifest)
    changed = manifest.model_copy(deep=True)
    changed.labs[0].catalog_release = "another-release"

    result = evaluate_event_order_schedule(
        changed, EventOrderSchedule.model_validate(payload)
    )

    assert result.eligible is False
    assert "schedule manifest digest does not match approved scope" in result.failures


def test_schedule_cannot_validate_manifest_with_wrong_approved_demand():
    manifest = _manifest()
    manifest.approval.approved_seat_environments = 90
    payload = _schedule(manifest)

    result = evaluate_event_order_schedule(
        manifest, EventOrderSchedule.model_validate(payload)
    )

    assert result.eligible is False
    assert "event approval does not match seat-environment demand" in result.failures


def test_schedule_requires_cohort_starts_and_approval_before_ordering():
    manifest = _manifest()
    payload = _schedule(manifest)
    manifest.cohorts[0].starts_at = None
    payload["approved_at"] = "2026-10-01T13:31:00Z"

    result = evaluate_event_order_schedule(
        manifest, EventOrderSchedule.model_validate(payload)
    )

    assert result.eligible is False
    assert "cohort session-1 has no scheduled start" in result.failures
    assert "schedule approval must precede every order window" in result.failures


def test_schedule_rejects_naive_or_reversed_order_windows():
    manifest = _manifest()
    payload = _schedule(manifest)
    payload["windows"][0]["not_before"] = "2026-10-01T13:30:00"
    payload["windows"][0]["not_after"] = "2026-10-01T13:00:00Z"

    result = evaluate_event_order_schedule(
        manifest, EventOrderSchedule.model_validate(payload)
    )

    assert result.eligible is False
    assert any("timezone-aware" in failure for failure in result.failures)
