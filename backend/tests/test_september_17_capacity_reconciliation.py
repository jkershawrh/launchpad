from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from app.services.event_capacity_reconciliation import reconcile_capacity_files

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "fixtures/events/september-17-2026.yaml"
POSTMORTEM = ROOT / "docs/september-17-pilot-postmortem.json"
CONTRACT = ROOT / "contracts/event-capacity-reconciliation-v1.yaml"


def test_recorded_september_17_reconciliation_is_deterministic_and_truthful():
    first = reconcile_capacity_files(MANIFEST, POSTMORTEM, root=ROOT)
    second = reconcile_capacity_files(MANIFEST, POSTMORTEM, root=ROOT)

    assert first == second
    assert first.event_id == "september-17-2026-pilot"
    assert first.observed_at.isoformat() == "2026-09-17T21:56:00+00:00"
    assert first.forecast.participant_count == 90
    assert first.forecast.workshop_count == 9
    assert first.forecast.seat_environments == 270
    assert first.observed.workshops_ordered == 9
    assert first.observed.workshops_ready_retained == 9
    assert first.observed.workshops_reclaimed == 0
    assert first.observed.seats_provisioned == 270
    assert first.observed.seats_claimed == 191
    assert first.observed.seats_unclaimed == 79
    assert first.variance.provisioned_seat_environments == 0
    assert first.variance.unclaimed_seat_environments == 79
    assert len(first.observed.clusters) == 3
    assert len(first.observed.models) == 3
    assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", item.sha256) for item in first.sources)
    assert {item.path for item in first.sources} == {
        "fixtures/events/september-17-2026.yaml",
        "docs/september-17-pilot-postmortem.json",
    }


def test_reconciliation_json_contains_no_participant_identity_or_false_usage_zero():
    result = reconcile_capacity_files(MANIFEST, POSTMORTEM, root=ROOT)
    payload = result.model_dump(mode="json")
    text = json.dumps(payload, sort_keys=True)

    assert "email" not in text.lower()
    assert "participant_id" not in text.lower()
    for field in (
        "actual_cpu_millicore_hours",
        "actual_memory_mib_hours",
        "actual_storage_gib_hours",
        "model_requests",
        "model_input_tokens",
        "model_output_tokens",
        "model_queue_seconds",
        "image_cache_hit_rate",
    ):
        assert payload["observed"][field]["status"] == "unavailable"
        assert payload["observed"][field]["value"] is None


def test_capacity_reconciliation_contract_names_sources_forecast_observed_and_variance():
    contract = yaml.safe_load(CONTRACT.read_text())
    schema = contract["components"]["schemas"]["CapacityReconciliation"]

    assert contract["info"]["version"] == "1.0.0"
    assert set(schema["required"]) == {
        "schema_version",
        "event_id",
        "observed_at",
        "sources",
        "forecast",
        "observed",
        "variance",
        "limitations",
    }
    measurement = contract["components"]["schemas"]["CapacityMeasurement"]
    assert set(measurement["properties"]["status"]["enum"]) == {
        "available",
        "unavailable",
    }
    assert measurement["properties"]["value"]["type"] == [
        "integer",
        "number",
        "string",
        "null",
    ]
