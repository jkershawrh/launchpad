import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/arena-granite-tools-four-replica-agent201-burst-20260911.json"
)


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text())


def test_four_replica_model_pool_is_live_and_evenly_spread():
    model_pool = _evidence()["model_pool"]

    assert model_pool["desired_replicas"] == 4
    assert model_pool["ready_replicas"] == 4
    assert model_pool["ready_endpoints"] == 4
    assert model_pool["restart_count"] == 0
    assert model_pool["placement"] == {
        "gnr2.fm2aihpcsed.com": 2,
        "rhgnr1": 2,
    }
    assert model_pool["pod_disruption_budget"]["min_available"] == 2


def test_model_endpoint_accepts_a_25_request_simultaneous_burst():
    burst = _evidence()["model_endpoint_burst"]

    assert burst["concurrency"] == 25
    assert burst["successful"] == burst["requests"] == 25
    assert burst["failed"] == 0
    assert len(burst["requests_observed_by_replica"]) == 4
    assert sum(burst["requests_observed_by_replica"]) == 25


def test_all_25_participant_workflows_complete_inside_gateway_timeout():
    evidence = _evidence()
    burst = evidence["participant_workflow_burst"]

    assert burst["concurrency"] == 25
    assert burst["successful"] == burst["requests"] == 25
    assert burst["failed"] == 0
    assert burst["p95_seconds"] < burst["gateway_timeout_seconds"]
    assert evidence["decision"]["result"] == (
        "GREEN-live-functional-with-latency-warning"
    )
    assert evidence["contains_plaintext_credentials"] is False


def test_certifier_harness_gap_does_not_relax_provisioner_permissions():
    observation = _evidence()["certifier_harness_observation"]

    assert observation["status"] == "follow-up-required"
    assert "Do not broaden" in observation["security_decision"]
