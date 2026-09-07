"""Contract for the first retained Arena 25+25 RED observation."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/september-17-arena-retained-25x2-20260907-red.json"


def test_retained_25x2_red_evidence_is_honest_and_actionable():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "RED-live-retained-25x2"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["contains_plaintext_credentials"] is False

    multi_agent = evidence["workshops"]["multi_agent"]
    assert multi_agent["requested_seats"] == 25
    assert multi_agent["seat_states"] == {"ready": 25}
    assert multi_agent["retained"] is True

    cpu_serving = evidence["workshops"]["cpu_serving"]
    assert cpu_serving["requested_seats"] == 25
    assert cpu_serving["seat_states"]["failed"] > 0
    assert cpu_serving["seat_states"]["ready"] < 25
    assert cpu_serving["retained"] is True

    capacity = evidence["capacity_preview"]
    assert capacity["can_provision"] is True
    assert capacity["selected_cluster"] == "arena"
    assert capacity["cluster_safe_seats_after_multi_agent_retained"] >= 25

    observation = evidence["cluster_observation"]
    assert observation["nodes_ready"] == 5
    assert observation["nodes_with_pressure"] == 0
    assert observation["model_endpoint_consecutive_http_200_probes"] == 5
    assert observation["concurrent_probe_failures_observed"] is True

    diagnosis = evidence["diagnosis"]
    assert diagnosis["capacity_exhaustion"] is False
    assert diagnosis["persistent_model_failure"] is False
    assert diagnosis["transient_service_or_node_network_instability"] is True

    matrix = {row["id"]: row for row in evidence["red_green_matrix"]}
    assert matrix["SEPT17-RETAINED-PREFLIGHT-001"]["status"] == "RED-live"
    assert matrix["SEPT17-RETAINED-PREFLIGHT-001"]["green_live"] is None
    assert matrix["SEPT17-RETAINED-FUNCTIONAL-001"]["status"] == "RED-not-run"
    assert matrix["SEPT17-RETAINED-CLEANUP-001"]["status"] == "RED-not-run"

    assert evidence["rubric"]["score"] < evidence["rubric"]["required"]
    assert evidence["rubric"]["release_gate"] == "failed"
    assert evidence["remediation"]["replacement_workshop_allowed"] is False
