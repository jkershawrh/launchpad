from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from app.domain.capacity_reconciliation import RecordedEventManifest
from app.services.event_capacity_reconciliation import build_capacity_forecast

ROOT = Path(__file__).parents[2]


def _manifest() -> RecordedEventManifest:
    source = yaml.safe_load((ROOT / "fixtures/events/september-17-2026.yaml").read_text())
    return RecordedEventManifest.model_validate(source)


def test_forecast_joins_cohorts_labs_retention_and_exact_catalog_releases():
    forecast = build_capacity_forecast(_manifest())

    assert forecast.cohort_count == 3
    assert forecast.participant_count == 90
    assert forecast.workshop_count == 9
    assert forecast.seat_environments == 270
    assert forecast.peak_concurrent_participants == 90
    assert forecast.peak_retained_environments == 270
    assert forecast.retention_hours == 168
    assert {item.catalog_id for item in forecast.catalogs} == {
        "intel-llm-cpu-serving",
        "intel-xeon6-agent-201",
        "multi-agent-quickstart",
    }
    assert {item.catalog_release for item in forecast.catalogs} == {"september-17-pilot"}
    assert all(item.seat_environments == 90 for item in forecast.catalogs)


def test_forecast_does_not_invent_missing_wave_schedule_or_deployment_class():
    forecast = build_capacity_forecast(_manifest())

    assert forecast.provisioning_waves.status == "available"
    assert forecast.provisioning_waves.value == 3
    assert forecast.wave_schedule.status == "unavailable"
    assert forecast.wave_schedule.value is None
    assert "starts_at" in forecast.wave_schedule.reason
    assert forecast.deployment_class.status == "unavailable"
    assert forecast.deployment_class.value is None
    assert "deployment class" in forecast.deployment_class.reason


def test_forecast_fails_closed_when_recorded_approval_does_not_match_demand():
    payload = yaml.safe_load((ROOT / "fixtures/events/september-17-2026.yaml").read_text())
    changed = deepcopy(payload)
    changed["spec"]["approval"]["approved_seat_environments"] = 90

    with pytest.raises(ValueError, match="approved 90 seat-environments.*requires 270"):
        build_capacity_forecast(RecordedEventManifest.model_validate(changed))
