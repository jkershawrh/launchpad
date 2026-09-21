"""RED/GREEN contract for a future read-only cluster accounting adapter."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.domain.clusters import ClusterTarget
from app.domain.events import EventCapacityReservation, EventResourceVector
from app.services.event_inflight_capacity_collector import (
    ClusterInventory,
    InflightCollectionBlocked,
    NamespaceInventory,
    PodRequest,
    collect_inflight_capacity,
    write_inflight_capacity_snapshot,
)
from app.services.event_inflight_capacity_provider import FileEventInflightCapacityProvider

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
TARGET = ClusterTarget(
    cluster_id="arena", display_name="Arena", ingress_domain="apps.arena.example.test"
)


def _reservation():
    return EventCapacityReservation(
        reservation_id="reserve-1",
        event_id="event-1",
        cohort_id="cohort-1",
        lab_ref="lab-1",
        catalog_id="catalog-1",
        catalog_release="v1",
        cluster_ref="arena",
        matrix_id="matrix-1",
        matrix_digest="sha256:digest",
        fleet_snapshot_id="fleet-1",
        resources=EventResourceVector(seats=1, cpu_millicores=1000, memory_mib=1024, pods=3),
        status="consumed",
        expires_at=NOW,
        consumed_at=NOW,
        workshop_id="workshop-1",
        created_at=NOW,
    )


def _inventory(labels=None):
    return ClusterInventory(
        cluster_id="arena",
        observed_at=NOW,
        allocatable_cpu_millicores=8000,
        allocatable_memory_mib=16000,
        allocatable_pods=100,
        allocatable_model_slots=0,
        namespaces=(
            NamespaceInventory(
                name="seat-namespace",
                labels=labels
                or {
                    "launchpad.redhat.com/event-reservation-id": "reserve-1",
                    "launchpad.redhat.com/workshop-id": "workshop-1",
                    "launchpad.redhat.com/seat-id": "seat-1",
                },
                pods=(PodRequest(uid="pod-1", cpu_millicores=100, memory_mib=256),),
            ),
        ),
        namespace_names=("seat-namespace",),
        node_inventory_complete=True,
        namespace_inventory_complete=True,
        pod_inventory_complete=True,
        request_inventory_complete=True,
        model_slot_inventory_complete=True,
    )


class FakeObserver:
    def __init__(self, inventory):
        self.inventory = inventory
        self.seen = []

    def observe(self, target):
        self.seen.append(target.cluster_id)
        return self.inventory


def _collect(inventory):
    return collect_inflight_capacity(
        [TARGET],
        [_reservation()],
        FakeObserver(inventory),
        now=NOW,
        persisted_seats={"workshop-1": {"seat-1"}},
    )


def test_complete_inventory_round_trips_through_trusted_file_provider(tmp_path):
    observer = FakeObserver(_inventory())
    document = collect_inflight_capacity(
        [TARGET],
        [_reservation()],
        observer,
        now=NOW,
        persisted_seats={"workshop-1": {"seat-1"}},
    )
    assert observer.seen == ["arena"]
    workload = document["clusters"][0]["workloads"][0]
    assert workload["reservation_id"] == "reserve-1"
    assert workload["workshop_id"] == "workshop-1"
    assert workload["seat_refs"] == ["seat-1"]
    assert workload["resources"] == {
        "cpu_millicores": 100,
        "memory_mib": 256,
        "pods": 1,
        "model_slots": 0,
    }
    output = tmp_path / "snapshot.json"
    write_inflight_capacity_snapshot(output, document)
    assert output.stat().st_mode & 0o777 == 0o600
    parsed = FileEventInflightCapacityProvider(output).load()
    assert parsed.clusters[0].accounting_complete is True
    assert parsed.clusters[0].workloads[0].reservation_id == "reserve-1"


@pytest.mark.parametrize(
    "field",
    [
        "node_inventory_complete",
        "namespace_inventory_complete",
        "pod_inventory_complete",
        "request_inventory_complete",
        "model_slot_inventory_complete",
    ],
)
def test_incomplete_inventory_is_blocked(field):
    inventory = _inventory()
    inventory = inventory.__class__(**{**inventory.__dict__, field: False})
    with pytest.raises(InflightCollectionBlocked, match="incomplete"):
        _collect(inventory)


def test_namespace_roster_gap_is_blocked():
    inventory = _inventory()
    inventory = inventory.__class__(**{**inventory.__dict__, "namespace_names": ("another",)})
    with pytest.raises(InflightCollectionBlocked, match="namespace roster"):
        _collect(inventory)


def test_missing_reservation_or_seat_label_is_blocked():
    for label in ("event-reservation-id", "seat-id"):
        labels = dict(_inventory().namespaces[0].labels)
        labels.pop(f"launchpad.redhat.com/{label}")
        with pytest.raises(InflightCollectionBlocked, match="identity"):
            _collect(_inventory(labels))


def test_orphan_workshop_label_cannot_be_counted_as_external_or_written(tmp_path):
    labels = {"launchpad.redhat.com/workshop-id": "unknown-workshop"}
    output = tmp_path / "snapshot.json"
    with pytest.raises(InflightCollectionBlocked, match="workshop identity"):
        document = _collect(_inventory(labels))
        write_inflight_capacity_snapshot(output, document)
    assert not output.exists()


@pytest.mark.parametrize(
    "labels",
    [
        {"launchpad.redhat.com/event-reservation-id": "reserve-1"},
        {"launchpad.redhat.com/seat-id": "seat-1"},
        {
            "launchpad.redhat.com/workshop-id": "workshop-1",
            "launchpad.redhat.com/seat-id": "seat-1",
        },
        {
            "launchpad.redhat.com/workshop-id": "unknown-workshop",
            "launchpad.redhat.com/event-reservation-id": "reserve-1",
        },
    ],
)
def test_partial_launchpad_identity_is_blocked(labels):
    with pytest.raises(InflightCollectionBlocked, match="identity"):
        _collect(_inventory(labels))


def test_mismatched_reservation_identity_is_blocked():
    labels = dict(_inventory().namespaces[0].labels)
    labels["launchpad.redhat.com/event-reservation-id"] = "wrong"
    with pytest.raises(InflightCollectionBlocked, match="identity"):
        _collect(_inventory(labels))


def test_unknown_cluster_and_duplicate_pod_are_blocked():
    inventory = _inventory()
    wrong = inventory.__class__(**{**inventory.__dict__, "cluster_id": "brutus"})
    with pytest.raises(InflightCollectionBlocked, match="cluster"):
        _collect(wrong)
    namespace = inventory.namespaces[0]
    duplicate = namespace.__class__(**{**namespace.__dict__, "pods": namespace.pods * 2})
    inventory = inventory.__class__(**{**inventory.__dict__, "namespaces": (duplicate,)})
    with pytest.raises(InflightCollectionBlocked, match="pod"):
        _collect(inventory)


def test_external_namespace_still_counts_all_pod_requests():
    inventory = _inventory()
    external = NamespaceInventory(
        name="external",
        labels={},
        pods=(PodRequest(uid="pod-external", cpu_millicores=500, memory_mib=512),),
    )
    inventory = inventory.__class__(
        **{
            **inventory.__dict__,
            "namespaces": inventory.namespaces + (external,),
            "namespace_names": inventory.namespace_names + ("external",),
        }
    )
    document = _collect(inventory)
    workload = next(
        item for item in document["clusters"][0]["workloads"] if item["namespace"] == "external"
    )
    assert workload["reservation_id"] is None
    assert workload["resources"]["cpu_millicores"] == 500


def test_failed_collection_never_replaces_previous_snapshot(tmp_path):
    output = tmp_path / "snapshot.json"
    original = _collect(_inventory())
    write_inflight_capacity_snapshot(output, original)
    before = output.read_bytes()
    with pytest.raises(InflightCollectionBlocked):
        _collect(None)
    assert output.read_bytes() == before


def test_unpersisted_seat_identity_is_blocked():
    with pytest.raises(InflightCollectionBlocked, match="persisted workshop seat"):
        collect_inflight_capacity(
            [TARGET],
            [_reservation()],
            FakeObserver(_inventory()),
            now=NOW,
            persisted_seats={},
        )


def test_cli_refuses_to_mint_snapshot_without_trusted_observer(tmp_path):
    output = tmp_path / "capacity.json"
    script = Path(__file__).resolve().parents[2] / "scripts" / "collect_event_inflight_capacity.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "no capacity snapshot was written" in result.stderr
    assert not output.exists()
