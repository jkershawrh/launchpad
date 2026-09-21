"""Fake Kubernetes reads prove exact release/node filtering without live calls."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Obj

import pytest
from app.domain.clusters import ClusterTarget
from app.services.cluster_registry import ClusterRegistry
from app.services.event_artifact_requirements import ArtifactRequirementSourceError
from app.services.event_eligible_node_source import (
    KubernetesEligibleNodeSource,
    TrustedWorkloadPlacement,
)

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


def node(
    name: str,
    *,
    labels=None,
    architecture="amd64",
    ready="True",
    cordoned=False,
    taints=None,
    conditions=None,
    ready_since=NOW - timedelta(hours=1),
):
    return Obj(
        metadata=Obj(
            name=name,
            labels={"kubernetes.io/arch": architecture, **(labels or {})},
        ),
        spec=Obj(unschedulable=cordoned, taints=taints or []),
        status=Obj(
            node_info=Obj(architecture=architecture),
            conditions=[Obj(type="Ready", status=ready, last_transition_time=ready_since)]
            + (conditions or []),
        ),
    )


class FakeCore:
    def __init__(self, nodes):
        self.nodes = nodes
        self.calls = 0
        self.metadata = Obj(resource_version="104", _continue="")

    def list_node(self, **kwargs):
        assert kwargs["_request_timeout"] == 10
        self.calls += 1
        return Obj(items=self.nodes, metadata=self.metadata)


class FakeFactory:
    def __init__(self, core):
        self.core = core
        self.cluster_ids = []

    def clients(self, cluster_id):
        self.cluster_ids.append(cluster_id)
        return Obj(core=self.core)


class PlacementSource:
    def __init__(self, policy):
        self.policy = policy

    def get_placement(self, catalog_id, catalog_release):
        assert (catalog_id, catalog_release) == ("build-agent", "v2")
        return self.policy


def source(nodes, policy=None, *, enabled=True):
    registry = ClusterRegistry(
        [
            ClusterTarget(
                cluster_id="brutus",
                display_name="Brutus",
                ingress_domain="apps.example.test",
                enabled=enabled,
            )
        ]
    )
    core = FakeCore(nodes)
    factory = FakeFactory(core)
    policy = policy or TrustedWorkloadPlacement(
        catalog_id="build-agent",
        catalog_release="v2",
        architecture="amd64",
        node_selector={"launchpad/workload": "agent"},
    )
    adapter = KubernetesEligibleNodeSource(
        registry, factory, PlacementSource(policy), clock=lambda: NOW
    )
    return adapter, core, factory


def read(adapter):
    return adapter.get_eligible_nodes("brutus", "build-agent", "v2")


def test_only_ready_schedulable_matching_architecture_and_labels_are_returned():
    nodes = [
        node("b", labels={"launchpad/workload": "agent"}),
        node("a", labels={"launchpad/workload": "agent"}),
        node("wrong-label"),
        node("wrong-arch", labels={"launchpad/workload": "agent"}, architecture="arm64"),
        node("cordoned", labels={"launchpad/workload": "agent"}, cordoned=True),
        node("unready", labels={"launchpad/workload": "agent"}, ready="False"),
        node(
            "pressure",
            labels={"launchpad/workload": "agent"},
            conditions=[Obj(type="DiskPressure", status="True")],
        ),
        node(
            "control",
            labels={"launchpad/workload": "agent", "node-role.kubernetes.io/control-plane": ""},
        ),
        node(
            "tainted",
            labels={"launchpad/workload": "agent"},
            taints=[Obj(key="dedicated", value="gpu", effect="NoSchedule")],
        ),
    ]
    adapter, core, factory = source(nodes)
    result = read(adapter)
    assert result.node_ids == ["a", "b"]
    assert result.observed_at == NOW
    assert factory.cluster_ids == ["brutus"]
    assert core.calls == 1


def test_required_affinity_is_or_of_terms_and_and_of_expressions():
    policy = TrustedWorkloadPlacement(
        catalog_id="build-agent",
        catalog_release="v2",
        architecture="amd64",
        required_affinity_terms=[
            {
                "match_expressions": [
                    {"key": "zone", "operator": "In", "values": ["a"]},
                    {"key": "tier", "operator": "Exists"},
                ]
            },
            {"match_expressions": [{"key": "pool", "operator": "In", "values": ["agent"]}]},
        ],
    )
    adapter, _, _ = source(
        [
            node("a", labels={"zone": "a", "tier": "regular"}),
            node("b", labels={"pool": "agent"}),
            node("c", labels={"zone": "a"}),
        ],
        policy,
    )
    assert read(adapter).node_ids == ["a", "b"]


def test_tolerated_taint_and_ready_dwell_are_enforced():
    policy = TrustedWorkloadPlacement(
        catalog_id="build-agent",
        catalog_release="v2",
        architecture="amd64",
        tolerations=[
            {"key": "dedicated", "operator": "Equal", "value": "agent", "effect": "NoSchedule"}
        ],
        min_ready_seconds=300,
    )
    adapter, _, _ = source(
        [
            node("ok", taints=[Obj(key="dedicated", value="agent", effect="NoSchedule")]),
            node("short-dwell", ready_since=NOW - timedelta(seconds=299)),
            node("wrong-taint", taints=[Obj(key="dedicated", value="gpu", effect="NoSchedule")]),
            node("noexecute", taints=[Obj(key="other", value="", effect="NoExecute")]),
        ],
        policy,
    )
    assert read(adapter).node_ids == ["ok"]


@pytest.mark.parametrize(
    "change",
    [
        "disabled",
        "missing-policy",
        "wrong-release",
        "empty",
        "partial",
        "no-version",
        "duplicate",
        "api-failure",
    ],
)
def test_unknown_or_incomplete_inputs_fail_closed(change):
    adapter, core, factory = source(
        [node("a", labels={"launchpad/workload": "agent"})], enabled=change != "disabled"
    )
    if change == "missing-policy":
        adapter.placements.policy = None
    elif change == "wrong-release":
        adapter.placements.policy = adapter.placements.policy.model_copy(
            update={"catalog_release": "v3"}
        )
    elif change == "empty":
        core.nodes = []
    elif change == "partial":
        core.metadata._continue = "token"
    elif change == "no-version":
        core.metadata.resource_version = ""
    elif change == "duplicate":
        core.nodes.append(core.nodes[0])
    elif change == "api-failure":
        factory.clients = lambda cluster_id: (_ for _ in ()).throw(
            RuntimeError("private credential detail")
        )
    with pytest.raises(ArtifactRequirementSourceError) as error:
        read(adapter)
    assert "private credential detail" not in str(error.value)
    if change == "disabled":
        assert core.calls == 0


def test_policy_rejects_unsupported_scheduler_rules_and_finite_tolerations():
    with pytest.raises(ValueError):
        TrustedWorkloadPlacement(
            catalog_id="build-agent",
            catalog_release="v2",
            architecture="amd64",
            unsupported_pod_affinity={"app": "foo"},
        )
    with pytest.raises(ValueError):
        TrustedWorkloadPlacement(
            catalog_id="build-agent",
            catalog_release="v2",
            architecture="amd64",
            tolerations=[
                {"key": "x", "operator": "Exists", "effect": "NoExecute", "toleration_seconds": 30}
            ],
        )


def test_observation_must_be_timezone_aware():
    adapter, _, _ = source([node("a", labels={"launchpad/workload": "agent"})])
    adapter.clock = lambda: datetime(2026, 9, 21, 12)  # noqa: DTZ001 - intentional invalid clock
    with pytest.raises(ArtifactRequirementSourceError, match="timezone"):
        read(adapter)
