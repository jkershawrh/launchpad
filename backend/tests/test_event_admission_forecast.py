from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from app.main import app

from app.services.event_reservations import (
    EventReservationConflictError,
    EventReservationLedger,
    build_event_reservation_plan,
    forecast_event_admission,
)

from backend.tests.test_event_reservation_ledger import NOW, _record, _supply


def test_forecast_contract_matches_provider_openapi():
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts/event-admission-forecast-v1.yaml").read_text()
    )
    generated = app.openapi()
    path = "/api/v1/events/{event_id}/admission-forecast"
    assert generated["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EventAdmissionForecast"
    }
    for schema in ("EventAdmissionForecast", "EventClusterAdmissionForecast", "EventResourceVector"):
        assert set(contract["components"]["schemas"][schema]["required"]) == set(
            generated["components"]["schemas"][schema].get("required", [])
        )


def test_forecast_reports_exact_remaining_multidimensional_capacity_without_mutation():
    supply = _supply(seats=90, cpu_millicores=90_000)
    record = _record("event-b", supply)
    ledger = EventReservationLedger()

    forecast = forecast_event_admission(
        record,
        supply,
        ledger.snapshot_active(),
        now=NOW,
    )

    assert forecast.status == "available"
    assert forecast.eligible is True
    assert forecast.evidence_matches is True
    assert forecast.current_active_reservations == 0
    assert len(forecast.clusters) == 1
    assert forecast.clusters[0].cluster_id == "arena"
    assert forecast.clusters[0].demand.seats == 60
    assert forecast.clusters[0].remaining_after_event.seats == 30
    assert forecast.clusters[0].required_capabilities == ["cpu", "model-endpoint"]
    assert ledger.snapshot_active() == []


def test_forecast_blocks_overcommit_created_by_another_event_reservation():
    supply = _supply(seats=90, cpu_millicores=90_000)
    ledger = EventReservationLedger()
    first = _record("event-a", supply)
    second = _record("event-b", supply)
    ledger.reserve(
        build_event_reservation_plan(
            first,
            supply,
            expires_at=NOW + timedelta(hours=8),
            now=NOW,
        ),
        supply,
        now=NOW,
    )

    forecast = forecast_event_admission(
        second,
        supply,
        ledger.snapshot_active(),
        now=NOW,
    )

    assert forecast.status == "blocked"
    assert forecast.eligible is False
    assert forecast.current_active_reservations == 2
    assert "seats" in forecast.clusters[0].blockers
    assert forecast.clusters[0].remaining_after_event.seats == 0


def test_forecast_fails_closed_on_capacity_evidence_drift():
    supply = _supply(seats=90, cpu_millicores=90_000)
    record = _record("event-a", supply)
    supply.matrix_digest = "sha256:" + "c" * 64

    forecast = forecast_event_admission(record, supply, [], now=NOW)

    assert forecast.status == "blocked"
    assert forecast.eligible is False
    assert forecast.evidence_matches is False
    assert forecast.clusters == []
    assert "changed after event approval" in forecast.explanation


def test_existing_reservation_does_not_double_count_its_own_demand():
    supply = _supply(seats=60)
    record = _record("event-a", supply)
    ledger = EventReservationLedger()
    ledger.reserve(
        build_event_reservation_plan(
            record, supply, expires_at=NOW + timedelta(hours=8), now=NOW
        ),
        supply,
        now=NOW,
    )

    forecast = forecast_event_admission(record, supply, ledger.snapshot_active(), now=NOW)

    assert forecast.status == "reserved"
    assert forecast.eligible is True
    assert forecast.clusters[0].demand.seats == 60
    assert forecast.clusters[0].reserved.seats == 0
    assert forecast.clusters[0].remaining_after_event.seats == 0


def test_existing_reservation_fails_closed_when_matrix_or_release_drifts():
    supply = _supply(seats=60)
    record = _record("event-a", supply)
    ledger = EventReservationLedger()
    ledger.reserve(
        build_event_reservation_plan(
            record, supply, expires_at=NOW + timedelta(hours=8), now=NOW
        ),
        supply,
        now=NOW,
    )
    supply.matrix_digest = "sha256:" + "c" * 64
    supply.clusters[0].catalogs.pop()

    forecast = forecast_event_admission(record, supply, ledger.snapshot_active(), now=NOW)

    assert forecast.status == "blocked"
    assert forecast.eligible is False
    assert forecast.evidence_matches is False
    assert "capacity_evidence_drift" in forecast.clusters[0].blockers
    assert "catalog:build-agent@v2" in forecast.clusters[0].blockers


def test_forecast_excludes_uncertified_model_capability_and_stale_fleet():
    supply = _supply(seats=60)
    record = _record("event-a", supply)
    supply.clusters[0].capabilities.remove("model-endpoint")

    uncertified = forecast_event_admission(record, supply, [], now=NOW)
    assert uncertified.status == "blocked"
    assert "model-endpoint" in uncertified.clusters[0].blockers

    supply.clusters[0].capabilities.append("model-endpoint")
    stale = forecast_event_admission(record, supply, [], now=NOW + timedelta(minutes=3))
    assert stale.status == "blocked"
    assert "stale" in stale.explanation


def test_forecast_fails_closed_when_exact_model_certification_is_removed():
    supply = _supply(seats=60)
    supply.clusters[0].certified_models = ["granite-3.2-8b-tools"]
    manifest = _record("event-a", supply).manifest
    manifest.labs[0].required_models = ["granite-3.2-8b-tools"]
    record = _record("event-a", supply).model_copy(update={"manifest": manifest})
    supply.clusters[0].certified_models = []

    forecast = forecast_event_admission(record, supply, [], now=NOW)

    assert forecast.status == "blocked"
    assert forecast.eligible is False
    assert "exact required model certification" in forecast.explanation
    assert forecast.clusters == []
    with pytest.raises(EventReservationConflictError, match="exact required model certification"):
        build_event_reservation_plan(
            record, supply, expires_at=NOW + timedelta(hours=8), now=NOW
        )


def test_forecast_blocks_expired_held_reservation_without_mutating_ledger():
    supply = _supply(seats=60)
    record = _record("event-a", supply)
    ledger = EventReservationLedger()
    ledger.reserve(
        build_event_reservation_plan(
            record, supply, expires_at=NOW + timedelta(minutes=1), now=NOW
        ),
        supply,
        now=NOW,
    )
    before = ledger.snapshot_active()

    forecast = forecast_event_admission(
        record, supply, before, now=NOW + timedelta(minutes=2)
    )

    assert forecast.status == "blocked"
    assert forecast.eligible is False
    assert ledger.snapshot_active() == before
