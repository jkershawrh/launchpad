"""Contract for the Arena retained 25+25 node-instability RED evidence."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT / "evidence/runs/september-17-arena-retained-25x2-20260907-node-instability-red.json"
)


def test_node_instability_evidence_blocks_false_certification():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "RED-live-node-instability"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["contains_plaintext_credentials"] is False

    cpu = evidence["workshops"]["cpu_serving"]
    assert cpu["api_seat_state_after_bounded_preflight_recovery"] == {"ready": 25}
    assert cpu["ready_sessions_preserved_during_retry"] == 16
    assert cpu["failed_seats_recovered_in_place"] == 9
    assert cpu["replacement_workshop_created"] is False

    first, second = evidence["cpu_participant_bursts"]
    assert first["simultaneous_seats"] == 25
    assert first["grounded_and_cited"] == 22
    assert first["failed"] == 3
    assert second["simultaneous_seats"] == 25
    assert second["failed"] == 25

    assert len(evidence["node_incidents"]) >= 2
    assert all(incident["node"] == "rhgnr1" for incident in evidence["node_incidents"])
    assert evidence["node_observation"]["memory_pressure"] is False
    assert evidence["node_observation"]["disk_pressure"] is False
    assert evidence["node_observation"]["pid_pressure"] is False
    assert evidence["node_observation"]["cross_component_probe_timeouts"] is True

    drift = evidence["lifecycle_drift_observation"]
    assert drift["expected_namespaces"] == 50
    assert (
        drift["active_namespaces"] + drift["terminating_namespaces"] == drift["namespaces_observed"]
    )
    assert drift["missing_namespaces"] > 0
    assert drift["initiator_confirmed"] is False

    diagnosis = evidence["diagnosis"]
    assert diagnosis["root_cause_confirmed"] is False
    assert diagnosis["stable_worker_network_or_runtime"] is False
    assert diagnosis["application_capacity_exhaustion"] is False

    matrix = {row["id"]: row for row in evidence["red_green_matrix"]}
    assert matrix["SEPT17-25X2-PROVISION-RECOVERY-001"]["status"] == "GREEN-live"
    assert matrix["SEPT17-25X2-PARTICIPANT-001"]["status"] == "RED-live"
    assert matrix["SEPT17-25X2-NODE-STABILITY-001"]["status"] == "RED-live"
    assert matrix["SEPT17-25X2-LIFECYCLE-001"]["status"] == "RED-live"
    assert matrix["SEPT17-25X2-CLEANUP-001"]["status"] == "RED-not-run"

    assert evidence["rubric"]["score"] < evidence["rubric"]["required"]
    assert evidence["rubric"]["release_gate"] == "failed"
