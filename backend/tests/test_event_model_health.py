from datetime import timedelta
import json

import pytest
import yaml

from app.domain.event_model_health import EventModelHealthSnapshot, ModelRuntimeHealth
from app.services.event_model_health import (
    EventModelHealthUnavailableError,
    FileEventModelHealthProvider,
    assess_event_model_health,
)
from app.services.event_reservations import (
    EventReservationConflictError,
    build_event_reservation_plan,
    forecast_event_admission,
)
from backend.tests.test_event_reservation_ledger import NOW, _record, _supply


def _model_event():
    supply = _supply()
    supply.clusters[0].certified_models = ["granite-8b"]
    record = _record("event-model", supply)
    record.manifest.labs[0].required_models = ["granite-8b"]
    return record, supply


def _health(**changes):
    values = dict(
        cluster_id="arena", model_id="granite-8b", ready_replicas=1,
        route_exposed=True, probe_success=True,
    )
    values.update(changes)
    return EventModelHealthSnapshot(
        snapshot_id="sha256:" + "d" * 64,
        observed_at=NOW,
        models=[ModelRuntimeHealth(**values)],
    )


def test_model_event_requires_fresh_runtime_evidence_for_reservation_and_forecast():
    record, supply = _model_event()
    forecast = forecast_event_admission(record, supply, [], now=NOW)
    assert forecast.status == "blocked"
    assert forecast.model_health_status == "blocked"
    assert "unavailable" in forecast.explanation
    with pytest.raises(EventReservationConflictError, match="unavailable"):
        build_event_reservation_plan(record, supply, expires_at=NOW + timedelta(hours=1), now=NOW)


def test_healthy_model_allows_same_certified_allocation():
    record, supply = _model_event()
    snapshot = _health()
    assessment = assess_event_model_health(record, snapshot, NOW)
    assert assessment.status == "ready"
    forecast = forecast_event_admission(record, supply, [], model_health=snapshot, now=NOW)
    assert forecast.status == "available"
    assert forecast.model_health_status == "ready"
    assert forecast.model_health_snapshot_id == snapshot.snapshot_id
    assert build_event_reservation_plan(
        record, supply, expires_at=NOW + timedelta(hours=1), model_health=snapshot, now=NOW
    ).reservations


@pytest.mark.parametrize(
    "snapshot,reason",
    [
        (_health(ready_replicas=0), "ready replica"),
        (_health(route_exposed=False), "route"),
        (_health(probe_success=False), "probe"),
        (_health(cluster_id="brutus"), "missing"),
        (_health(model_id="other-model"), "missing"),
        (_health().model_copy(update={"observed_at": NOW - timedelta(minutes=3)}), "stale"),
    ],
)
def test_runtime_failures_block_model_event(snapshot, reason):
    record, supply = _model_event()
    assessment = assess_event_model_health(record, snapshot, NOW)
    assert assessment.status == "blocked"
    assert reason in assessment.explanation
    with pytest.raises(EventReservationConflictError, match=reason):
        build_event_reservation_plan(
            record, supply, expires_at=NOW + timedelta(hours=1), model_health=snapshot, now=NOW
        )


def test_model_free_event_needs_no_runtime_model_snapshot():
    supply = _supply()
    record = _record("event-no-model", supply)
    assert assess_event_model_health(record, None, NOW).status == "not_required"
    assert forecast_event_admission(record, supply, [], now=NOW).status == "available"


def test_duplicate_runtime_model_evidence_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        EventModelHealthSnapshot(
            snapshot_id="sha256:" + "d" * 64,
            observed_at=NOW,
            models=[_health().models[0], _health().models[0]],
        )


def test_runtime_snapshot_producer_contract_lists_required_fields():
    from pathlib import Path

    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts/event-model-health-v1.yaml").read_text()
    )
    assert contract["schema_version"] == "1.0"
    assert set(contract["model_row_required"]) == set(ModelRuntimeHealth.model_fields)
    assert set(contract["required"]) == {"schema_version", "observed_at", "models"}


def test_file_provider_hashes_server_owned_snapshot_and_rejects_invalid_file(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({
        "schema_version": "1.0", "observed_at": NOW.isoformat(),
        "models": [_health().models[0].model_dump()],
    }))
    loaded = FileEventModelHealthProvider(str(path)).load()
    assert loaded.snapshot_id.startswith("sha256:")
    assert loaded.models[0].model_id == "granite-8b"
    path.write_text('{"schema_version":"1.0","models":[]}')
    with pytest.raises(EventModelHealthUnavailableError):
        FileEventModelHealthProvider(str(path)).load()


def test_api_model_event_fails_closed_then_accepts_fresh_injected_health():
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from app.api import deps
    from app.auth.oauth import User, get_current_user
    from app.main import app
    from app.services.event_reservations import EventReservationLedger
    from app.services.events import EventManifestStore

    record, supply = _model_event()
    supply.fleet_observed_at = datetime.now(UTC)
    store = EventManifestStore()
    store.create(record)
    app.dependency_overrides[deps.get_event_capacity_supply] = lambda: supply
    app.dependency_overrides[deps.get_event_manifest_store] = lambda: store
    app.dependency_overrides[deps.get_event_reservation_ledger] = lambda: EventReservationLedger()
    app.dependency_overrides[deps.get_event_model_health_snapshot] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: User(username="admin", is_admin=True)
    client = TestClient(app)
    url = "/api/v1/events/event-model"
    try:
        blocked = client.get(url + "/admission-forecast")
        rejected = client.post(url + "/reservations", json={
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        })
        assert blocked.status_code == 200
        assert blocked.json()["model_health_status"] == "blocked"
        assert rejected.status_code == 409
        fresh = _health().model_copy(update={"observed_at": datetime.now(UTC)})
        app.dependency_overrides[deps.get_event_model_health_snapshot] = lambda: fresh
        accepted = client.post(url + "/reservations", json={
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        })
        assert accepted.status_code == 201
    finally:
        for dependency in (
            deps.get_event_capacity_supply, deps.get_event_manifest_store,
            deps.get_event_reservation_ledger, deps.get_event_model_health_snapshot,
            get_current_user,
        ):
            app.dependency_overrides.pop(dependency, None)
