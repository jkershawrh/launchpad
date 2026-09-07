import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/intel-cpu-serving-five-seat-arena-20260907.json"
CHECKSUM = EVIDENCE.with_suffix(".json.sha256")


def _evidence():
    return json.loads(EVIDENCE.read_text())


def test_current_cpu_serving_release_passes_five_seat_functional_gate():
    evidence = _evidence()

    assert evidence["result"] == "GREEN-live-five-seat"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["catalog_version"] == "1.0.1"
    assert evidence["seat_count"] == 5
    assert evidence["provisioning"]["all_seats_ready"] is True
    assert evidence["provisioning"]["collective_ready_seconds"] <= 120
    assert evidence["provisioning"]["showroom_http_200"] == 5
    assert evidence["provisioning"]["guide_http_200"] == 5
    assert evidence["provisioning"]["runtime_contract_complete"] == 5
    assert evidence["provisioning"]["anythingllm_ready"] == 5
    assert evidence["provisioning"]["container_restarts"] == 0


def test_five_seat_repeatability_preserves_the_latency_red_observation():
    rag = _evidence()["concurrent_rag"]

    assert rag["total_calls"] == 20
    assert rag["successful_calls"] == 20
    assert rag["grounded_answers"] == 20
    assert rag["cited_documents"] == 20
    assert rag["bursts"][0]["classification"] == "RED-performance-observation"
    assert rag["bursts"][0]["nearest_rank_p95_seconds"] > 10
    assert rag["consecutive_qualifying_bursts"] == 3
    assert rag["qualifying_calls"] == 15
    assert rag["qualifying_nearest_rank_p95_seconds"] < 10
    assert all(burst["nearest_rank_p95_seconds"] < 10 for burst in rag["bursts"][1:])


def test_five_seat_isolation_and_bulk_reclaim_are_complete():
    evidence = _evidence()
    authorization = evidence["authorization"]
    cleanup = evidence["cleanup"]

    assert authorization["default_project_matches_seat"] == 5
    assert authorization["own_namespace_edit_allowed"] == 5
    assert authorization["cross_seat_read_denied"] == 5
    assert cleanup["workshop_status"] == "completed"
    assert cleanup["reclaimed_seats"] == 5
    assert cleanup["zero_residue_observed_seconds"] <= 600
    assert cleanup["remaining_namespaces"] == 0
    assert cleanup["remaining_routes"] == 0
    assert cleanup["remaining_applications"] == 0
    assert cleanup["remaining_rolebindings"] == 0
    assert cleanup["remaining_pods"] == 0
    assert cleanup["remaining_secrets"] == 0
    assert cleanup["forced_finalizers"] == 0


def test_five_seat_evidence_has_complete_proof_matrix_and_no_overclaim():
    evidence = _evidence()

    assert set(evidence["proof_strategy"]) == {"tdd", "edd", "cdd", "bdd", "cbt"}
    assert evidence["rubric"]["score"] == evidence["rubric"]["required"] == 100
    assert "twenty-five-seat current-release CPU-serving workshop" in evidence["not_certified"]
    assert "three-workshop September 17 fleet rehearsal" in evidence["not_certified"]
    assert evidence["contains_plaintext_credentials"] is False
    assert all(
        row["red"] and row["green_local"] and row["green_live"]
        for row in evidence["red_green_matrix"]
    )


def test_five_seat_evidence_checksum_matches():
    expected = CHECKSUM.read_text().split()[0]
    actual = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
    assert actual == expected
