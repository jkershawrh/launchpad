"""Proof contract for the September 17 read-only fleet preflight."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/september_17_multicluster_preflight.py"
SPEC = importlib.util.spec_from_file_location("september_17_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(
        self,
        selected_clusters: list[str],
        *,
        unhealthy_clusters: set[str] | None = None,
        available_pods: dict[str, int] | None = None,
    ):
        self.selected_clusters = iter(selected_clusters)
        self.unhealthy_clusters = unhealthy_clusters or set()
        self.available_pods = available_pods or {
            "arena": 284,
            "oberon": 140,
            "brutus": 141,
        }
        self.requests: list[dict] = []

    def get(self, url: str, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return FakeResponse(
            200,
            {
                "mutates_cluster": False,
                "clusters": [
                    {
                        "cluster_id": cluster_id,
                        "healthy": cluster_id not in self.unhealthy_clusters,
                        "configured_enabled": cluster_id == "arena",
                        "available_cpu_millicores": 400000,
                        "available_memory_mib": 1400000,
                        "available_pods": self.available_pods[cluster_id],
                    }
                    for cluster_id in ("arena", "oberon", "brutus")
                ],
            },
        )

    def post(self, url: str, **kwargs):
        self.requests.append({"url": url, **kwargs})
        selected = next(self.selected_clusters)
        return FakeResponse(
            200,
            {
                "can_provision": True,
                "selected_cluster": selected,
                "placement_reason": (
                    f"Entire workshop assigned to {selected}; seats will not be split"
                ),
            },
        )


def test_contract_preflight_builds_three_explicit_non_public_capacity_requests():
    contract = MODULE.load_event_contract()
    requests = MODULE.build_capacity_requests(contract)

    assert [(request["catalog_item_id"], request["target_cluster"]) for request in requests] == [
        ("multi-agent-quickstart", "arena"),
        ("intel-llm-cpu-serving", "arena"),
        ("intel-xeon6-agent-201", "brutus"),
    ]
    assert all(request["num_users"] == 25 for request in requests)
    assert all(request["exposure_policy"] == "internal" for request in requests)
    assert all(request["certification_override"] is False for request in requests)


def test_live_preflight_is_green_only_when_every_preview_keeps_exact_affinity():
    contract = MODULE.load_event_contract()
    session = FakeSession(["arena", "arena", "brutus"])

    result = MODULE.run_capacity_preflight(
        contract,
        api_base_url="https://launchpad-api.example.com",
        api_key="not-a-real-key",
        session=session,
    )

    assert result["result"] == "GREEN-live-preflight"
    assert result["mutates_cluster"] is False
    assert result["target_inspection"]["passed"] is True
    assert result["aggregate_capacity"]["passed"] is True
    assert result["aggregate_capacity"]["clusters"]["arena"]["passed"] is True
    assert len(result["checks"]) == 3
    assert all(check["passed"] for check in result["checks"])
    assert all(request["headers"]["X-API-Key"] == "not-a-real-key" for request in session.requests)


def test_live_preflight_fails_closed_on_cluster_substitution():
    contract = MODULE.load_event_contract()
    session = FakeSession(["arena", "brutus", "brutus"])

    result = MODULE.run_capacity_preflight(
        contract,
        api_base_url="https://launchpad-api.example.com/api/v1",
        api_key="not-a-real-key",
        session=session,
    )

    assert result["result"] == "RED"
    assert result["checks"][1]["passed"] is False
    assert result["checks"][1]["selected_cluster"] == "brutus"
    assert result["checks"][1]["expected_cluster"] == "arena"


def test_live_preflight_is_red_when_disabled_target_inspection_is_unhealthy():
    contract = MODULE.load_event_contract()
    session = FakeSession(
        ["arena", "arena", "brutus"],
        unhealthy_clusters={"brutus"},
    )

    result = MODULE.run_capacity_preflight(
        contract,
        api_base_url="https://launchpad-api.example.com",
        api_key="not-a-real-key",
        session=session,
    )

    assert result["result"] == "RED"
    assert result["target_inspection"]["passed"] is False
    assert result["target_inspection"]["targets"]["brutus"]["healthy"] is False


def test_live_preflight_is_red_when_individual_previews_pass_but_aggregate_does_not_fit():
    contract = MODULE.load_event_contract()
    session = FakeSession(
        ["arena", "arena", "brutus"],
        available_pods={"arena": 119, "oberon": 140, "brutus": 141},
    )

    result = MODULE.run_capacity_preflight(
        contract,
        api_base_url="https://launchpad-api.example.com",
        api_key="not-a-real-key",
        session=session,
    )

    assert all(check["passed"] for check in result["checks"])
    assert result["aggregate_capacity"]["passed"] is False
    assert result["aggregate_capacity"]["clusters"]["arena"]["passed"] is False
    assert result["result"] == "RED"


def test_contract_validation_requires_declared_two_cluster_workshop_counts():
    contract = copy.deepcopy(MODULE.load_event_contract())
    contract["candidate_cluster_workshop_counts"]["arena"] = 1

    try:
        MODULE.build_capacity_requests(contract)
    except ValueError as exc:
        assert "workshop counts" in str(exc)
    else:
        raise AssertionError("invalid two-cluster event distribution was accepted")
