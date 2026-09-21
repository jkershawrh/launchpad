from pathlib import Path

import pytest
import yaml
from app.api import deps
from app.domain.events import (
    EventCapacitySupply,
    EventCatalogCapacity,
    EventClusterCapacity,
    EventManifest,
    calculate_event_capacity,
)
from app.main import app
from app.services.events import EventManifestStore
from app.storage.stores import PersistenceUnavailableError
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[2]
CONTRACT = ROOT / "contracts" / "event-manifest-v1.yaml"
PILOT = ROOT / "fixtures" / "events" / "september-17-2026.yaml"
MIGRATION = ROOT / "backend" / "migrations" / "007_event_manifests.sql"


def test_event_manifest_contract_requires_unambiguous_capacity_inputs():
    contract = yaml.safe_load(CONTRACT.read_text())
    schema = contract["components"]["schemas"]["EventManifest"]

    assert contract["info"]["version"] == "1.5.0"
    assert "required_models" in contract["components"]["schemas"]["EventLab"]["properties"]
    assert "required_models" in contract["components"]["schemas"]["EventCatalogCapacity"]["properties"]
    assert "certified_models" in contract["components"]["schemas"]["EventClusterCapacity"]["properties"]
    generated = app.openapi()["components"]["schemas"]
    assert "required_models" in generated["EventLab"]["properties"]
    assert "required_models" in EventCatalogCapacity.model_json_schema()["properties"]
    assert "certified_models" in EventClusterCapacity.model_json_schema()["properties"]
    assert {
        "event_id",
        "name",
        "owner",
        "technical_approver",
        "cohorts",
        "labs",
        "retention",
        "exposure_policy",
        "placement_policy",
    } <= set(schema["required"])

    preview = contract["components"]["schemas"]["EventCapacityPreview"]
    assert {
        "matrix_id",
        "matrix_digest",
        "fleet_snapshot_id",
        "fleet_observed_at",
        "participant_count",
        "seat_environments",
        "peak_concurrent_participants",
        "peak_retained_environments",
        "certified_capacity",
        "dr_reserved_capacity",
        "uncertified_capacity",
        "allocations",
        "lab_capacity",
    } <= set(preview["required"])
    created = contract["paths"]["/api/v1/events"]["post"]["responses"]["201"]
    assert created["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EventRecord"
    }


def test_event_migration_keeps_approved_manifest_immutable():
    migration = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS event_manifests" in migration
    assert "event_id   TEXT PRIMARY KEY" in migration
    assert "ON CONFLICT" not in migration


def test_september_pilot_example_exposes_the_scope_change_and_flightpath_pivot():
    manifest = yaml.safe_load(PILOT.read_text())
    cohorts = manifest["spec"]["cohorts"]
    labs = manifest["spec"]["labs"]

    participant_count = sum(item["participants"] for item in cohorts)
    seat_environments = sum(item["participants"] * len(item["lab_refs"]) for item in cohorts)

    assert len(cohorts) == 3
    assert len(labs) == 3
    assert participant_count == 90
    assert seat_environments == 270
    assert manifest["status"]["originally_understood_seat_environments"] == 90
    assert manifest["status"]["required_seat_environments"] == 270
    assert manifest["status"]["additional_seat_environments"] == 180
    assert manifest["status"]["flightpath_role_before_event"] == "dr_candidate"
    assert manifest["status"]["flightpath_event_role"] == "emergency_execution"
    assert manifest["status"]["production_certified_before_pivot"] is False


def test_event_manifest_requires_human_approval_before_capacity_reservation():
    manifest = yaml.safe_load(PILOT.read_text())
    approval = manifest["spec"]["approval"]

    assert approval["event_owner_approved"] is True
    assert approval["technical_approver_approved"] is True
    assert approval["approved_seat_environments"] == 270
    assert approval["approved_retention_hours"] == 168


def _pilot_manifest() -> EventManifest:
    return EventManifest.model_validate(yaml.safe_load(PILOT.read_text())["spec"])


def _pilot_supply(
    *,
    certified_capacity: int = 270,
    dr_reserved_capacity: int = 0,
    uncertified_capacity: int = 0,
    enabled: bool = True,
) -> EventCapacitySupply:
    manifest = _pilot_manifest()
    return EventCapacitySupply(
        matrix_id="pilot-test-matrix",
        matrix_digest="sha256:" + "a" * 64,
        clusters=[
            EventClusterCapacity(
                cluster_id="certified-event-pool",
                enabled=enabled,
                exposure_policies=["internal", "public_code"],
                capabilities=[],
                certified_seats=certified_capacity,
                dr_reserved_seats=dr_reserved_capacity,
                uncertified_seats=uncertified_capacity,
                catalogs=[
                    EventCatalogCapacity(
                        catalog_id=lab.catalog_id,
                        catalog_release=lab.catalog_release,
                        certified_seats=certified_capacity,
                    )
                    for lab in manifest.labs
                ],
            )
        ]
    )


def test_event_capacity_calculation_distinguishes_people_from_environments():
    preview = calculate_event_capacity(
        _pilot_manifest(),
        _pilot_supply(),
    )

    assert preview.participant_count == 90
    assert preview.seat_environments == 270
    assert preview.peak_concurrent_participants == 30
    assert preview.peak_retained_environments == 270
    assert preview.eligible is True


def test_dr_reserved_and_uncertified_capacity_never_make_event_eligible():
    preview = calculate_event_capacity(
        _pilot_manifest(),
        _pilot_supply(
            certified_capacity=90,
            dr_reserved_capacity=90,
            uncertified_capacity=90,
        ),
    )

    assert preview.eligible is False
    assert preview.capacity_shortfall == 180
    assert "DR-reserved" in preview.explanation
    assert "uncertified" in preview.explanation


def test_event_capacity_rejects_approval_for_the_wrong_number_of_environments():
    manifest = _pilot_manifest()
    manifest.approval.approved_seat_environments = 90

    with pytest.raises(ValueError, match="approved 90 seat-environments but requires 270"):
        calculate_event_capacity(
            manifest,
            _pilot_supply(),
        )


def test_event_capacity_preview_fails_closed_without_server_owned_supply():
    response = TestClient(app).post(
        "/api/v1/events/capacity-preview",
        json=_pilot_manifest().model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["seat_environments"] == 270
    assert response.json()["certified_capacity"] == 0
    assert response.json()["eligible"] is False


def test_event_capacity_preview_uses_server_owned_certified_supply():
    app.dependency_overrides[deps.get_event_capacity_supply] = lambda: _pilot_supply(
        certified_capacity=270,
        dr_reserved_capacity=180,
        uncertified_capacity=90,
    )
    try:
        response = TestClient(app).post(
            "/api/v1/events/capacity-preview",
            json=_pilot_manifest().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(deps.get_event_capacity_supply, None)

    assert response.status_code == 200
    assert response.json()["eligible"] is True
    assert response.json()["certified_capacity"] == 270
    assert response.json()["dr_reserved_capacity"] == 180
    assert response.json()["uncertified_capacity"] == 90


def test_event_capacity_preview_returns_bad_request_for_approval_mismatch():
    payload = _pilot_manifest().model_dump(mode="json")
    payload["approval"]["approved_seat_environments"] = 90

    response = TestClient(app).post(
        "/api/v1/events/capacity-preview",
        json=payload,
    )

    assert response.status_code == 400
    assert "approved 90 seat-environments but requires 270" in response.json()["detail"]


def test_create_event_persists_approved_manifest_without_lifecycle_mutation():
    store = EventManifestStore()
    app.dependency_overrides[deps.get_event_capacity_supply] = _pilot_supply
    app.dependency_overrides[deps.get_event_manifest_store] = lambda: store
    try:
        response = TestClient(app).post(
            "/api/v1/events",
            json=_pilot_manifest().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(deps.get_event_capacity_supply, None)
        app.dependency_overrides.pop(deps.get_event_manifest_store, None)

    assert response.status_code == 201
    assert response.json()["manifest"]["event_id"] == "september-17-2026-pilot"
    assert response.json()["capacity_preview"]["seat_environments"] == 270
    assert response.json()["capacity_preview"]["matrix_id"] == "pilot-test-matrix"
    assert response.json()["capacity_preview"]["matrix_digest"] == "sha256:" + "a" * 64
    assert len(response.json()["capacity_preview"]["allocations"]) == 9
    assert all(
        allocation["seats"] == 30
        for allocation in response.json()["capacity_preview"]["allocations"]
    )
    assert store.get("september-17-2026-pilot") is not None


def test_create_event_rejects_uncertified_capacity_before_persistence():
    store = EventManifestStore()
    app.dependency_overrides[deps.get_event_capacity_supply] = lambda: _pilot_supply(
        certified_capacity=90,
        dr_reserved_capacity=180,
    )
    app.dependency_overrides[deps.get_event_manifest_store] = lambda: store
    try:
        response = TestClient(app).post(
            "/api/v1/events",
            json=_pilot_manifest().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(deps.get_event_capacity_supply, None)
        app.dependency_overrides.pop(deps.get_event_manifest_store, None)

    assert response.status_code == 409
    assert store.get("september-17-2026-pilot") is None


def test_event_id_is_immutable_and_duplicate_create_conflicts():
    store = EventManifestStore()
    app.dependency_overrides[deps.get_event_capacity_supply] = _pilot_supply
    app.dependency_overrides[deps.get_event_manifest_store] = lambda: store
    try:
        first = TestClient(app).post(
            "/api/v1/events",
            json=_pilot_manifest().model_dump(mode="json"),
        )
        duplicate = TestClient(app).post(
            "/api/v1/events",
            json=_pilot_manifest().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(deps.get_event_capacity_supply, None)
        app.dependency_overrides.pop(deps.get_event_manifest_store, None)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_create_event_fails_closed_when_durable_storage_is_unavailable():
    class UnavailableStore:
        def create(self, _record):
            raise PersistenceUnavailableError("database unavailable")

    app.dependency_overrides[deps.get_event_capacity_supply] = _pilot_supply
    app.dependency_overrides[deps.get_event_manifest_store] = UnavailableStore
    try:
        response = TestClient(app).post(
            "/api/v1/events",
            json=_pilot_manifest().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(deps.get_event_capacity_supply, None)
        app.dependency_overrides.pop(deps.get_event_manifest_store, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Approved event persistence is unavailable"
