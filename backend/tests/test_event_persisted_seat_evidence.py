"""Persisted roster evidence must fail closed before physical accounting."""

from datetime import UTC, datetime, timedelta

import pytest
from app.domain.events import EventCapacityReservation, EventResourceVector
from app.domain.models import LabSession, Workshop, WorkshopSeat
from app.services.event_inflight_capacity_collector import InflightCollectionBlocked
from app.services.event_persisted_seat_evidence import (
    PersistedRosterSnapshot,
    collect_persisted_seat_evidence,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def reservation(**changes):
    fields = {
        "reservation_id": "reservation-1",
        "event_id": "event-1",
        "cohort_id": "cohort-1",
        "lab_ref": "lab-1",
        "catalog_id": "lab-catalog",
        "catalog_release": "v1",
        "cluster_ref": "arena",
        "matrix_id": "matrix-1",
        "matrix_digest": "digest-1",
        "fleet_snapshot_id": "fleet-1",
        "resources": EventResourceVector(seats=2),
        "status": "consumed",
        "expires_at": NOW + timedelta(hours=4),
        "created_at": NOW - timedelta(minutes=10),
        "consumed_at": NOW - timedelta(seconds=30),
        "workshop_id": "workshop-1",
    }
    fields.update(changes)
    return EventCapacityReservation(**fields)


def snapshot(**changes):
    seats = [
        WorkshopSeat(workshop_id="workshop-1", seat_id="seat-1", seat_number=1),
        WorkshopSeat(workshop_id="workshop-1", seat_id="seat-2", seat_number=2),
    ]
    workshop = Workshop(
        workshop_id="workshop-1",
        tenant_id="tenant-1",
        catalog_item_id="lab-catalog",
        num_users=2,
        cluster_ref="arena",
        seats=seats,
    )
    fields = {"observed_at": NOW, "workshops": (workshop,), "sessions": ()}
    fields.update(changes)
    return PersistedRosterSnapshot(**fields)


class Source:
    def __init__(self, evidence):
        self.evidence = evidence

    def observe(self):
        return self.evidence


def collect(evidence=None, reservations=None):
    return collect_persisted_seat_evidence(
        Source(evidence or snapshot()), reservations or [reservation()], now=NOW
    )


def test_complete_persisted_roster_matches_collector_contract():
    assert collect() == {"workshop-1": {"seat-1", "seat-2"}}


@pytest.mark.parametrize(
    "change",
    [
        {"observed_at": NOW - timedelta(seconds=121)},
        {"observed_at": NOW + timedelta(seconds=31)},
        {"observed_at": NOW.replace(tzinfo=None)},
        {"workshops_complete": False},
        {"workshops_complete": 1},
        {"sessions_complete": False},
        {"workshops": ()},
    ],
)
def test_rejects_stale_or_partial_snapshot(change):
    with pytest.raises(InflightCollectionBlocked):
        collect(snapshot(**change))


def test_rejects_snapshot_predating_reservation_consumption():
    with pytest.raises(InflightCollectionBlocked):
        collect(snapshot(observed_at=NOW - timedelta(seconds=40)))


@pytest.mark.parametrize(
    "updates",
    [
        {"cluster_ref": "brutus"},
        {"cluster_ref": None},
        {"catalog_item_id": "wrong-catalog"},
        {"num_users": 1},
        {"seats": []},
        {"seats": [WorkshopSeat(workshop_id="workshop-1", seat_id="seat-1", seat_number=1)] * 2},
        {
            "seats": [
                WorkshopSeat(workshop_id="workshop-1", seat_id="seat-1", seat_number=1),
                WorkshopSeat(workshop_id="workshop-1", seat_id="seat-2", seat_number=3),
            ]
        },
    ],
)
def test_rejects_mismatched_or_incomplete_workshop(updates):
    base = snapshot()
    workshop = base.workshops[0].model_copy(update=updates)
    with pytest.raises(InflightCollectionBlocked):
        collect(snapshot(workshops=(workshop,)))


def test_rejects_duplicate_workshop_records():
    base = snapshot()
    with pytest.raises(InflightCollectionBlocked):
        collect(snapshot(workshops=(base.workshops[0], base.workshops[0])))


def test_rejects_two_reservations_binding_same_workshop():
    duplicate = reservation(reservation_id="reservation-2")
    with pytest.raises(InflightCollectionBlocked):
        collect(reservations=[reservation(), duplicate])


def test_rejects_missing_or_cross_cluster_session():
    base = snapshot()
    seats = list(base.workshops[0].seats)
    seats[0] = seats[0].model_copy(update={"session_id": "session-1"})
    workshop = base.workshops[0].model_copy(update={"seats": seats, "session_ids": ["session-1"]})
    with pytest.raises(InflightCollectionBlocked):
        collect(snapshot(workshops=(workshop,)))
    session = LabSession(
        session_id="session-1",
        request_id="request-1",
        tenant_id="tenant-1",
        catalog_item_id="lab-catalog",
        cluster_ref="brutus",
    )
    with pytest.raises(InflightCollectionBlocked):
        collect(snapshot(workshops=(workshop,), sessions=(session,)))
    session = session.model_copy(update={"cluster_ref": "arena"})
    assert collect(snapshot(workshops=(workshop,), sessions=(session,))) == {
        "workshop-1": {"seat-1", "seat-2"}
    }
