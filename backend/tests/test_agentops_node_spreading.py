from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem, LabRequest


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/agentops-observability/catalog-item.yaml"


def _node(
    name: str,
    *,
    labels: dict[str, str] | None = None,
    ready: bool = True,
    ready_for_seconds: int = 3600,
    unschedulable: bool = False,
    taints: tuple[SimpleNamespace, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, labels=labels or {}),
        spec=SimpleNamespace(unschedulable=unschedulable, taints=list(taints)),
        status=SimpleNamespace(
            allocatable={"pods": "250"},
            conditions=[
                SimpleNamespace(
                    type="Ready",
                    status="True" if ready else "False",
                    last_transition_time=(
                        datetime.now(timezone.utc)
                        - timedelta(seconds=ready_for_seconds)
                    ),
                ),
                SimpleNamespace(type="MemoryPressure", status="False"),
                SimpleNamespace(type="DiskPressure", status="False"),
                SimpleNamespace(type="PIDPressure", status="False"),
            ],
        ),
    )


def _pod(node: str, phase: str = "Running") -> SimpleNamespace:
    return SimpleNamespace(
        spec=SimpleNamespace(node_name=node),
        status=SimpleNamespace(phase=phase),
    )


def _agentops_item() -> CatalogItem:
    document = yaml.safe_load(CATALOG.read_text())
    return CatalogItem(**document)


def _adapter(nodes: list[SimpleNamespace], pods: list[SimpleNamespace]):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    adapter._target = SimpleNamespace(cluster_id="arena")
    adapter._core_v1 = MagicMock()
    adapter._core_v1.list_node.return_value = SimpleNamespace(items=nodes)
    adapter._core_v1.list_pod_for_all_namespaces.return_value = SimpleNamespace(
        items=pods
    )
    return adapter


def _seat_request(seat_number: int) -> LabRequest:
    return LabRequest(
        tenant_id="smoke-test-tenant",
        requester_id=f"participant-{seat_number}",
        catalog_item_id="agentops-observability",
        requested_mode=CatalogCategory.GUIDED_BUILD,
        metadata={"seat_number": seat_number, "workshop_id": "workshop-1"},
    )


def test_decommissioned_agentops_catalog_retains_safe_node_sharding_metadata():
    item = _agentops_item()

    assert item.status == CatalogStatus.DEPRECATED
    assert item.metadata["workshop_node_spread"] is True
    assert item.metadata["workshop_node_min_ready_seconds"] == 900
    assert item.metadata["workshop_node_headroom_pods"] == 10
    assert item.metadata["workshop_node_required_labels"] == {
        "launchpad.redhat.com/agentops-certified": "true"
    }
    assert item.metadata["workshop_provision_concurrency"] == 2


def test_agentops_seats_use_only_health_qualified_workers():
    nodes = [
        _node("rhgnr1"),
        _node(
            "gnr2.fm2aihpcsed.com",
            labels={"launchpad.redhat.com/agentops-certified": "true"},
        ),
    ]
    pods = [_pod("rhgnr1") for _ in range(176)] + [
        _pod("gnr2.fm2aihpcsed.com") for _ in range(41)
    ]
    adapter = _adapter(nodes, pods)
    item = _agentops_item()

    first = adapter.create_plan(_seat_request(1), item)
    second = adapter.create_plan(_seat_request(2), item)
    third = adapter.create_plan(_seat_request(3), item)

    assert first.required_resources["workshop_node_name"] == "gnr2.fm2aihpcsed.com"
    assert second.required_resources["workshop_node_name"] == "gnr2.fm2aihpcsed.com"
    assert third.required_resources["workshop_node_name"] == "gnr2.fm2aihpcsed.com"


def test_recently_recovered_or_pressured_workers_are_excluded():
    labels = {"launchpad.redhat.com/agentops-certified": "true"}
    recently_recovered = _node(
        "rhgnr1", labels=labels, ready_for_seconds=60
    )
    stable = _node("gnr2.fm2aihpcsed.com", labels=labels)
    adapter = _adapter([recently_recovered, stable], [])

    plan = adapter.create_plan(_seat_request(2), _agentops_item())

    assert plan.required_resources["workshop_node_name"] == "gnr2.fm2aihpcsed.com"


def test_agentops_node_sharding_fails_closed_without_a_stable_worker():
    control_plane_taint = SimpleNamespace(
        key="node-role.kubernetes.io/master", effect="NoSchedule"
    )
    adapter = _adapter(
        [
            _node(
                "control-plane",
                labels={"launchpad.redhat.com/agentops-certified": "true"},
                taints=(control_plane_taint,),
            ),
            _node(
                "recovering-worker",
                labels={"launchpad.redhat.com/agentops-certified": "true"},
                ready_for_seconds=30,
            ),
        ],
        [],
    )

    with pytest.raises(ValueError, match="No stable schedulable worker"):
        adapter.create_plan(_seat_request(1), _agentops_item())


def test_agentops_node_sharding_reserves_the_transient_seat_burst():
    node = _node(
        "gnr2.fm2aihpcsed.com",
        labels={"launchpad.redhat.com/agentops-certified": "true"},
    )
    # The candidate steady seat plus node headroom consumes 22 slots, but its
    # four-pod rollout burst raises the admission requirement to 26.
    pods = [_pod("gnr2.fm2aihpcsed.com") for _ in range(225)]
    adapter = _adapter([node], pods)

    with pytest.raises(ValueError, match="protected pod capacity"):
        adapter.create_plan(_seat_request(1), _agentops_item())


def test_selected_worker_is_applied_as_an_openshift_project_node_selector():
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._core_v1 = MagicMock()

    adapter._create_namespace(
        "agentops-seat",
        {"launchpad.redhat.com/workshop-id": "workshop-1"},
        {"openshift.io/node-selector": "kubernetes.io/hostname=rhgnr1"},
    )

    body = adapter._core_v1.create_namespace.call_args.kwargs["body"]
    assert body.metadata.annotations == {
        "openshift.io/node-selector": "kubernetes.io/hostname=rhgnr1"
    }
