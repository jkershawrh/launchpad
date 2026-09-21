"""The collector must never infer missing rows to make reclaim look safe."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.services.reclaim_inventory_collector import (
    CollectionBatch,
    InventoryCollectionError,
    build_reclaim_inventory,
)
from app.services.reclaim_readiness import evaluate_reclaim_readiness

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
WORKSHOP = str(UUID("11111111-1111-4111-8111-111111111111"))
SESSION = str(UUID("22222222-2222-4222-8222-222222222222"))


class FakeSource:
    def __init__(self):
        self.clusters = CollectionBatch(
            [{"cluster_ref": "arena"}, {"cluster_ref": "brutus"}], True, NOW
        )
        self.workshops = CollectionBatch(
            [
                {
                    "workshop_id": WORKSHOP,
                    "cluster_ref": "arena",
                    "seat_count": 1,
                    "reservation_id": "event:cohort:lab",
                    "state": "ready",
                    "instructor_code": "must-never-appear",
                }
            ],
            True,
            NOW,
        )
        self.sessions = CollectionBatch(
            [
                {
                    "session_id": SESSION,
                    "workshop_id": WORKSHOP,
                    "cluster_ref": "arena",
                    "namespace": "launchpad-seat-1",
                    "seat_number": 1,
                    "state": "ready",
                    "email": "private@example.org",
                }
            ],
            True,
            NOW,
        )
        self.reservations = CollectionBatch(
            [
                {
                    "reservation_id": "event:cohort:lab",
                    "workshop_id": WORKSHOP,
                    "cluster_ref": "arena",
                    "seat_count": 1,
                    "state": "consumed",
                }
            ],
            True,
            NOW,
        )
        self.namespaces = {
            "arena": CollectionBatch(
                [
                    {
                        "namespace": "launchpad-seat-1",
                        "cluster_ref": "arena",
                        "workshop_id": WORKSHOP,
                        "session_id": SESSION,
                        "token": "must-never-appear",
                    }
                ],
                True,
                NOW,
            ),
            "brutus": CollectionBatch([], True, NOW),
        }
        self.calls = []

    def list_cluster_refs(self):
        return self.clusters

    def list_retained_workshops(self):
        return self.workshops

    def list_sessions(self, workshop_ids):
        self.calls.append(("sessions", workshop_ids))
        return self.sessions

    def list_reservations(self, workshop_ids):
        self.calls.append(("reservations", workshop_ids))
        return self.reservations

    def list_managed_namespaces(self, cluster_ref):
        self.calls.append(("namespaces", cluster_ref))
        return self.namespaces[cluster_ref]


def test_complete_cross_cluster_inventory_is_balanced_and_minimized():
    source = FakeSource()
    payload = build_reclaim_inventory(source, now=NOW)
    assert evaluate_reclaim_readiness(payload, now=NOW).ready
    assert payload["scope"]["cluster_refs"] == ["arena", "brutus"]
    assert ("namespaces", "arena") in source.calls
    assert ("namespaces", "brutus") in source.calls
    assert "must-never-appear" not in str(payload)
    assert "private@example.org" not in str(payload)


@pytest.mark.parametrize("attribute", ["clusters", "workshops", "sessions", "reservations"])
def test_incomplete_roster_fails_closed(attribute):
    source = FakeSource()
    setattr(source, attribute, replace(getattr(source, attribute), complete=False))
    with pytest.raises(InventoryCollectionError, match="incomplete"):
        build_reclaim_inventory(source, now=NOW)


def test_incomplete_cluster_observation_fails_closed():
    source = FakeSource()
    source.namespaces["brutus"] = replace(source.namespaces["brutus"], complete=False)
    with pytest.raises(InventoryCollectionError, match="incomplete"):
        build_reclaim_inventory(source, now=NOW)


def test_missing_registered_cluster_observation_fails_closed():
    source = FakeSource()
    del source.namespaces["brutus"]
    with pytest.raises(InventoryCollectionError):
        build_reclaim_inventory(source, now=NOW)


def test_cross_cluster_namespace_targeting_fails_closed():
    source = FakeSource()
    source.namespaces["arena"] = CollectionBatch([], True, NOW)
    source.namespaces["brutus"] = CollectionBatch(
        [
            {
                "namespace": "launchpad-seat-1",
                "cluster_ref": "brutus",
                "workshop_id": WORKSHOP,
                "session_id": SESSION,
            }
        ],
        True,
        NOW,
    )
    with pytest.raises(InventoryCollectionError, match="namespace"):
        build_reclaim_inventory(source, now=NOW)


def test_missing_session_and_namespace_fails_even_if_provider_claims_complete():
    source = FakeSource()
    source.sessions = CollectionBatch([], True, NOW)
    source.namespaces["arena"] = CollectionBatch([], True, NOW)
    with pytest.raises(InventoryCollectionError, match="seat count"):
        build_reclaim_inventory(source, now=NOW)


def test_stale_component_blocks_entire_snapshot():
    source = FakeSource()
    source.namespaces["arena"] = replace(
        source.namespaces["arena"], observed_at=NOW - timedelta(minutes=31)
    )
    with pytest.raises(InventoryCollectionError, match="stale"):
        build_reclaim_inventory(source, now=NOW)


def test_empty_retained_roster_fails_closed():
    source = FakeSource()
    source.workshops = CollectionBatch([], True, NOW)
    with pytest.raises(InventoryCollectionError, match="empty"):
        build_reclaim_inventory(source, now=NOW)


def test_unregistered_persisted_cluster_fails_closed():
    source = FakeSource()
    source.clusters = CollectionBatch([{"cluster_ref": "brutus"}], True, NOW)
    with pytest.raises(InventoryCollectionError, match="cluster coverage"):
        build_reclaim_inventory(source, now=NOW)


def test_malformed_roster_identifier_fails_closed_without_type_error():
    source = FakeSource()
    source.workshops = CollectionBatch(
        [{**source.workshops.rows[0], "workshop_id": ["not-a-uuid"]}], True, NOW
    )
    with pytest.raises(InventoryCollectionError, match="invalid"):
        build_reclaim_inventory(source, now=NOW)


def test_malformed_state_fails_closed_without_type_error():
    source = FakeSource()
    source.workshops = CollectionBatch(
        [{**source.workshops.rows[0], "state": ["ready"]}], True, NOW
    )
    with pytest.raises(InventoryCollectionError, match="invalid"):
        build_reclaim_inventory(source, now=NOW)


def test_provider_exception_does_not_expose_secret():
    source = FakeSource()

    def failed(_cluster_ref):
        raise RuntimeError("token=private-secret")

    source.list_managed_namespaces = failed
    with pytest.raises(InventoryCollectionError) as caught:
        build_reclaim_inventory(source, now=NOW)
    assert "private-secret" not in str(caught.value)


def test_snapshot_that_ages_out_during_collection_is_rejected():
    source = FakeSource()
    with pytest.raises(InventoryCollectionError, match="stale"):
        build_reclaim_inventory(
            source,
            now=NOW,
            clock=lambda: NOW + timedelta(minutes=31),
        )
