from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api import deps
from app.auth.oauth import User, get_current_user
from app.main import app
from app.services.event_reservations import EventReservationLedger
from app.services.events import EventManifestStore
from fastapi.testclient import TestClient

from backend.tests.test_event_reservation_ledger import NOW, _record, _supply


def _overrides(*, admin: bool = True):
    supply = _supply()
    supply.fleet_observed_at = datetime.now(UTC)
    event_store = EventManifestStore()
    event_store.create(_record("event-a", supply))
    ledger = EventReservationLedger()
    app.dependency_overrides[deps.get_event_capacity_supply] = lambda: supply
    app.dependency_overrides[deps.get_event_manifest_store] = lambda: event_store
    app.dependency_overrides[deps.get_event_reservation_ledger] = lambda: ledger
    app.dependency_overrides[get_current_user] = lambda: User(
        username="event-admin" if admin else "event-viewer",
        is_admin=admin,
    )
    return supply, event_store, ledger


def _clear_overrides():
    for dependency in (
        deps.get_event_capacity_supply,
        deps.get_event_manifest_store,
        deps.get_event_reservation_ledger,
        get_current_user,
    ):
        app.dependency_overrides.pop(dependency, None)


def test_admin_approves_and_reserves_persisted_cluster_assignments():
    _supply_value, _event_store, ledger = _overrides()
    try:
        response = TestClient(app).post(
            "/api/v1/events/event-a/reservations",
            json={"expires_at": (NOW + timedelta(hours=8)).isoformat()},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 201
    assert response.json()["event_id"] == "event-a"
    assert response.json()["fleet_snapshot_id"] == "sha256:" + "b" * 64
    assert {item["cluster_ref"] for item in response.json()["reservations"]} == {
        "arena"
    }
    assert len(ledger.list_active(now=NOW)) == 2


def test_reservation_requires_admin_and_existing_approved_event():
    _overrides(admin=False)
    try:
        forbidden = TestClient(app).post(
            "/api/v1/events/event-a/reservations",
            json={"expires_at": (NOW + timedelta(hours=8)).isoformat()},
        )
    finally:
        _clear_overrides()
    assert forbidden.status_code == 403

    _overrides()
    try:
        missing = TestClient(app).post(
            "/api/v1/events/missing/reservations",
            json={"expires_at": (NOW + timedelta(hours=8)).isoformat()},
        )
    finally:
        _clear_overrides()
    assert missing.status_code == 404


def test_release_requires_positive_cleanup_evidence_and_is_idempotent():
    supply, event_store, _ledger = _overrides()
    event_store.create(_record("event-b", supply))
    try:
        held = TestClient(app).post(
            "/api/v1/events/event-a/reservations",
            json={"expires_at": (NOW + timedelta(hours=8)).isoformat()},
        )
        unsafe = TestClient(app).post(
            "/api/v1/events/event-a/reservations/release",
            json={"cleanup_completed": False, "cleanup_evidence_id": "proof-a"},
        )
        released = TestClient(app).post(
            "/api/v1/events/event-a/reservations/release",
            json={
                "cleanup_completed": True,
                "cleanup_evidence_id": "evidence:cleanup:event-a",
            },
        )
        repeated = TestClient(app).post(
            "/api/v1/events/event-a/reservations/release",
            json={
                "cleanup_completed": True,
                "cleanup_evidence_id": "evidence:cleanup:event-a",
            },
        )
        second = TestClient(app).post(
            "/api/v1/events/event-b/reservations",
            json={"expires_at": (NOW + timedelta(hours=8)).isoformat()},
        )
    finally:
        _clear_overrides()

    assert unsafe.status_code == 422
    assert held.status_code == 201
    assert released.status_code == 200
    assert released.json() == {
        "event_id": "event-a",
        "released_reservations": 2,
        "cleanup_evidence_id": "evidence:cleanup:event-a",
    }
    assert repeated.status_code == 200
    assert repeated.json()["released_reservations"] == 0
    assert second.status_code == 201
    assert len(second.json()["reservations"]) == 2
