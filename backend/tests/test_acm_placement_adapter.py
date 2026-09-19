from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from app.adapters.acm.placement import (
    AcmPlacementAdapter,
    AcmPlacementUnavailableError,
)


class FakeCustomObjectsApi:
    def __init__(self, decisions: list[dict], clusters: dict[str, dict]) -> None:
        self.decisions = decisions
        self.clusters = clusters

    def list_namespaced_custom_object(self, **kwargs):
        assert kwargs == {
            "group": "cluster.open-cluster-management.io",
            "version": "v1beta1",
            "namespace": "launchpad-fleet",
            "plural": "placementdecisions",
            "label_selector": "cluster.open-cluster-management.io/placement=launchpad-events",
        }
        return {"items": self.decisions}

    def get_cluster_custom_object(self, **kwargs):
        return self.clusters[kwargs["name"]]


def _decision(name: str, clusters: list[tuple[str, str]]) -> dict:
    return {
        "metadata": {"name": name, "resourceVersion": f"rv-{name}"},
        "status": {
            "decisions": [
                {"clusterName": cluster, "reason": reason}
                for cluster, reason in clusters
            ]
        },
    }


def _cluster(
    name: str,
    *,
    available: bool = True,
    accepted: bool = True,
) -> dict:
    return {
        "metadata": {
            "name": name,
            "resourceVersion": f"rv-{name}",
            "labels": {
                "vendor": "OpenShift",
                "launchpad.intel.com/cpu": "true",
            },
        },
        "status": {
            "conditions": [
                {
                    "type": "ManagedClusterConditionAvailable",
                    "status": "True" if available else "False",
                    "reason": "ManagedClusterAvailable"
                    if available
                    else "ManagedClusterUnavailable",
                },
                {
                    "type": "HubAcceptedManagedCluster",
                    "status": "True" if accepted else "False",
                    "reason": "HubClusterAdminAccepted",
                },
            ],
            "clusterClaims": [
                {"name": "platform.open-cluster-management.io", "value": "OpenShift"},
                {"name": "version.openshift.io", "value": "4.20"},
            ],
        },
    }


def test_adapter_returns_auditable_selected_and_rejected_clusters():
    api = FakeCustomObjectsApi(
        decisions=[
            _decision("decision-2", [("flightpath", "Balance")]),
            _decision("decision-1", [("arena", "Steady"), ("arena", "Duplicate")]),
        ],
        clusters={
            "arena": _cluster("arena"),
            "flightpath": _cluster("flightpath", available=False),
        },
    )

    snapshot = AcmPlacementAdapter(
        api,
        namespace="launchpad-fleet",
        placement_name="launchpad-events",
    ).snapshot()

    assert snapshot.eligible_cluster_ids == ["arena"]
    assert [item.cluster_id for item in snapshot.clusters] == ["arena", "flightpath"]
    assert snapshot.clusters[0].acm_eligible is True
    assert snapshot.clusters[1].acm_eligible is False
    assert "ManagedClusterConditionAvailable is not True" in snapshot.clusters[1].reasons
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot.snapshot_id)
    serialized = snapshot.model_dump_json()
    assert "credential" not in serialized
    assert "token" not in serialized
    assert "api_url" not in serialized


def test_snapshot_is_deterministic_across_decision_order():
    clusters = {"arena": _cluster("arena"), "brutus": _cluster("brutus")}
    first = AcmPlacementAdapter(
        FakeCustomObjectsApi(
            [_decision("b", [("brutus", "B")]), _decision("a", [("arena", "A")])],
            clusters,
        ),
        namespace="launchpad-fleet",
        placement_name="launchpad-events",
    ).snapshot()
    second = AcmPlacementAdapter(
        FakeCustomObjectsApi(
            [_decision("a", [("arena", "A")]), _decision("b", [("brutus", "B")])],
            clusters,
        ),
        namespace="launchpad-fleet",
        placement_name="launchpad-events",
    ).snapshot()

    assert first.snapshot_id == second.snapshot_id
    assert first.eligible_cluster_ids == ["arena", "brutus"]


def test_missing_hub_acceptance_fails_cluster_closed():
    snapshot = AcmPlacementAdapter(
        FakeCustomObjectsApi(
            [_decision("one", [("arena", "Selected")])],
            {"arena": _cluster("arena", accepted=False)},
        ),
        namespace="launchpad-fleet",
        placement_name="launchpad-events",
    ).snapshot()

    assert snapshot.eligible_cluster_ids == []
    assert "HubAcceptedManagedCluster is not True" in snapshot.clusters[0].reasons


def test_acm_api_failure_is_not_converted_to_an_empty_healthy_snapshot():
    class FailedApi:
        def list_namespaced_custom_object(self, **_kwargs):
            raise RuntimeError("hub unavailable")

    with pytest.raises(AcmPlacementUnavailableError, match="hub unavailable"):
        AcmPlacementAdapter(
            FailedApi(),
            namespace="launchpad-fleet",
            placement_name="launchpad-events",
        ).snapshot()


def test_snapshot_contract_keeps_capacity_and_credentials_out_of_acm_boundary():
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts" / "acm-placement-v1.yaml").read_text()
    )
    schemas = contract["components"]["schemas"]

    assert contract["info"]["version"] == "1.0.0"
    assert "AcmPlacementSnapshot" in schemas
    observation = schemas["AcmClusterObservation"]["properties"]
    assert "certified_seats" not in observation
    assert "credential" not in observation
    assert "api_url" not in observation
