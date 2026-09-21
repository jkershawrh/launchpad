"""Fake-cluster RED/GREEN proof; these tests never connect to OpenShift."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Obj

import pytest
from app.domain.clusters import ClusterTarget
from app.domain.events import EventCapacityReservation, EventResourceVector
from app.services.event_inflight_capacity_collector import (
    InflightCollectionBlocked,
    collect_inflight_capacity,
)
from app.services.event_kubernetes_inventory_observer import (
    KubernetesClusterInventoryObserver,
    ModelSlotObservation,
)

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)
TARGET = ClusterTarget(cluster_id="arena", display_name="Arena", ingress_domain="apps.arena.test")


def page(items, *, version="100", continuation=""):
    return Obj(items=items, metadata=Obj(resource_version=version, _continue=continuation))


def node(name="worker-1", *, ready=True, cordoned=False, allocatable=None, taints=None):
    return Obj(
        metadata=Obj(name=name, labels={"node-role.kubernetes.io/worker": ""}),
        spec=Obj(unschedulable=cordoned, taints=taints or []),
        status=Obj(
            conditions=[Obj(type="Ready", status="True" if ready else "False")],
            allocatable=allocatable or {"cpu": "8", "memory": "16Gi", "pods": "250"},
        ),
    )


def namespace(name="seat-one", *, labels=None):
    return Obj(metadata=Obj(name=name, labels=labels or {}))


def container(cpu="250m", memory="128Mi", *, restart_policy=None):
    return Obj(
        resources=Obj(requests={"cpu": cpu, "memory": memory}),
        restart_policy=restart_policy,
    )


def pod(
    uid="pod-1", *, phase="Running", name="seat-one", containers=None, init=None, overhead=None
):
    return Obj(
        metadata=Obj(uid=uid, namespace=name),
        status=Obj(phase=phase),
        spec=Obj(
            containers=containers if containers is not None else [container()],
            init_containers=init or [],
            overhead=overhead or {},
        ),
    )


class FakeCore:
    def __init__(self):
        self.nodes = page([node()])
        self.namespaces = page([namespace()])
        self.pods = page([pod()])
        self.calls = []

    def list_node(self, **kwargs):
        self.calls.append(("nodes", kwargs))
        return self.nodes

    def list_namespace(self, **kwargs):
        self.calls.append(("namespaces", kwargs))
        return self.namespaces

    def list_pod_for_all_namespaces(self, **kwargs):
        self.calls.append(("pods", kwargs))
        return self.pods


class FakeFactory:
    def __init__(self, core):
        self.core = core
        self.cluster_ids = []

    def clients(self, cluster_id):
        self.cluster_ids.append(cluster_id)
        return Obj(core=self.core)


class FakeSlots:
    def __init__(self, slots=0, *, complete=True, observed_at=NOW, cluster_id="arena"):
        self.result = ModelSlotObservation(
            cluster_id=cluster_id,
            observed_at=observed_at,
            allocatable_slots=slots,
            complete=complete,
        )
        self.seen = []

    def observe_model_slots(self, target):
        self.seen.append(target.cluster_id)
        return self.result


def observer(core=None, slots=None):
    core = core or FakeCore()
    factory = FakeFactory(core)
    slots = slots or FakeSlots()
    return (
        KubernetesClusterInventoryObserver(factory, slots, clock=lambda: NOW),
        core,
        factory,
        slots,
    )


def test_complete_read_only_inventory_counts_effective_pod_requests():
    adapter, core, factory, slots = observer()
    core.nodes = page(
        [
            node(),
            node("cordoned", cordoned=True),
            node("unready", ready=False),
            node("tainted", taints=[Obj(effect="NoSchedule")]),
        ]
    )
    core.pods = page(
        [
            pod(
                init=[container("100m", "64Mi", restart_policy="Always"), container("1", "512Mi")],
                overhead={"cpu": "10m", "memory": "8Mi"},
            ),
            pod("pod-pending", phase="Pending", containers=[container("500m", "256Mi")]),
            pod("pod-done", phase="Succeeded"),
        ]
    )

    inventory = adapter.observe(TARGET)

    assert factory.cluster_ids == ["arena"]
    assert slots.seen == ["arena"]
    assert [name for name, _ in core.calls] == ["nodes", "namespaces", "pods", "namespaces"]
    assert inventory.allocatable_cpu_millicores == 8000
    assert inventory.allocatable_memory_mib == 16384
    assert inventory.allocatable_pods == 250
    assert inventory.allocatable_model_slots == 0
    assert inventory.namespace_names == ("seat-one",)
    assert inventory.node_inventory_complete
    assert inventory.namespace_inventory_complete
    assert inventory.pod_inventory_complete
    assert inventory.request_inventory_complete
    assert inventory.model_slot_inventory_complete
    assert [
        (item.uid, item.cpu_millicores, item.memory_mib) for item in inventory.namespaces[0].pods
    ] == [
        ("pod-1", 1110, 584),
        ("pod-pending", 500, 256),
    ]


def test_missing_or_stale_model_slots_never_becomes_complete():
    for slots in (
        FakeSlots(complete=False),
        FakeSlots(observed_at=NOW - timedelta(minutes=3)),
        FakeSlots(observed_at="invalid"),
        FakeSlots(cluster_id="brutus"),
    ):
        adapter, _, _, _ = observer(slots=slots)
        with pytest.raises(InflightCollectionBlocked, match="model slot"):
            adapter.observe(TARGET)


def test_node_allocatable_rounds_down_while_pod_requests_round_up():
    adapter, core, _, _ = observer()
    core.nodes = page([node(allocatable={"cpu": "1.0001", "memory": "1.5Mi", "pods": "2"})])
    core.pods = page([pod(containers=[container("0.0001", "0.5Mi")])])

    inventory = adapter.observe(TARGET)

    assert inventory.allocatable_cpu_millicores == 1000
    assert inventory.allocatable_memory_mib == 1
    assert inventory.namespaces[0].pods[0].cpu_millicores == 1
    assert inventory.namespaces[0].pods[0].memory_mib == 1


def test_paginated_cluster_reads_prove_all_pages_were_consumed():
    adapter, core, _, _ = observer()
    first_page = page([pod("pod-1")], continuation="next")
    last_page = page([pod("pod-2")])

    def paginated_pods(**kwargs):
        return last_page if kwargs.get("_continue") == "next" else first_page

    core.list_pod_for_all_namespaces = paginated_pods

    inventory = adapter.observe(TARGET)

    assert {pod.uid for pod in inventory.namespaces[0].pods} == {"pod-1", "pod-2"}


def test_namespace_roster_drift_during_scan_blocks_evidence():
    adapter, core, _, _ = observer()
    calls = 0

    def changing_namespaces(**_kwargs):
        nonlocal calls
        calls += 1
        return page([namespace("seat-one" if calls == 1 else "seat-two")])

    core.list_namespace = changing_namespaces
    with pytest.raises(InflightCollectionBlocked, match="changed"):
        adapter.observe(TARGET)


def test_malformed_namespace_labels_do_not_become_an_empty_identity():
    adapter, core, _, _ = observer()
    core.namespaces = page([namespace(labels=["not-a-map"])])
    with pytest.raises(InflightCollectionBlocked, match="namespace inventory"):
        adapter.observe(TARGET)


def test_observer_feeds_collector_without_an_event_seat():
    adapter, core, _, _ = observer()
    core.namespaces = page([namespace(labels={"launchpad.redhat.com/workshop-id": "ordinary"})])

    document = collect_inflight_capacity([TARGET], [], adapter, now=NOW, persisted_seats={})

    workload = document["clusters"][0]["workloads"][0]
    assert workload["reservation_id"] is None
    assert workload["resources"]["cpu_millicores"] == 250
    assert document["clusters"][0]["accounting_complete"] is True


def test_observer_and_collector_reject_unlabeled_active_event_seat():
    adapter, core, _, _ = observer()
    core.namespaces = page(
        [namespace(labels={"launchpad.redhat.com/workshop-id": "event-workshop"})]
    )
    reservation = EventCapacityReservation(
        reservation_id="reservation-1",
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
        workshop_id="event-workshop",
        created_at=NOW,
    )

    with pytest.raises(InflightCollectionBlocked, match="identity"):
        collect_inflight_capacity(
            [TARGET],
            [reservation],
            adapter,
            now=NOW,
            persisted_seats={"event-workshop": {"seat-1"}},
        )


@pytest.mark.parametrize(
    "broken",
    [
        "no-version",
        "continuation",
        "missing-namespace",
        "bad-request",
        "api-failure",
        "no-ready-node",
        "disabled",
    ],
)
def test_incomplete_cluster_reads_fail_closed(broken):
    adapter, core, _, _ = observer()
    target = TARGET.model_copy(update={"enabled": False}) if broken == "disabled" else TARGET
    if broken == "no-version":
        core.namespaces = page([namespace()], version="")
    elif broken == "continuation":
        core.pods = page([pod()], continuation="next")
    elif broken == "missing-namespace":
        core.pods = page([pod(name="not-in-roster")])
    elif broken == "bad-request":
        core.pods = page([pod(containers=[container(cpu="invalid")])])
    elif broken == "api-failure":

        def unavailable(**_kwargs):
            raise RuntimeError("API unavailable")

        core.list_node = unavailable
    elif broken == "no-ready-node":
        core.nodes = page([node(ready=False)])
    with pytest.raises(InflightCollectionBlocked):
        adapter.observe(target)
