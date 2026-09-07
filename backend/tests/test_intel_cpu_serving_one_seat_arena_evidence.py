import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/intel-cpu-serving-one-seat-arena-20260907.json"
CHECKSUM = EVIDENCE.with_suffix(".json.sha256")


def _evidence():
    return json.loads(EVIDENCE.read_text())


def test_arena_cpu_serving_one_seat_proves_runtime_and_participant_journey():
    evidence = _evidence()

    assert evidence["result"] == "GREEN-live-one-seat"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["catalog_version"] == "1.0.1"
    assert evidence["runtime_contract"]["all_values_present"] is True
    assert evidence["runtime_contract"]["secret_serialized_in_antora_or_argocd"] is False
    assert evidence["participant_validation"]["terminal_own_namespace_edit"] is True
    assert evidence["participant_validation"]["terminal_default_namespace_read"] is False
    assert evidence["participant_validation"]["grounded_rag_http_status"] == 200
    assert evidence["participant_validation"]["expected_fact_returned"] is True
    assert evidence["participant_validation"]["source_document_cited"] is True


def test_arena_cpu_serving_one_seat_reclaim_has_zero_residue():
    cleanup = _evidence()["cleanup"]

    assert cleanup["workshop_status"] == "completed"
    assert cleanup["session_status"] == "reclaimed"
    assert cleanup["zero_residue_observed_seconds"] <= 600
    assert cleanup["remaining_namespaces"] == 0
    assert cleanup["remaining_routes"] == 0
    assert cleanup["remaining_applications"] == 0
    assert cleanup["remaining_rolebindings"] == 0
    assert cleanup["remaining_pods"] == 0
    assert cleanup["remaining_secrets"] == 0


def test_arena_cpu_serving_one_seat_records_proof_methods_without_overclaiming():
    evidence = _evidence()

    assert set(evidence["proof_strategy"]) == {"tdd", "edd", "cdd", "bdd", "cbt"}
    assert evidence["rubric"] == {
        "score": 100,
        "required": 100,
        "scope": "one-seat-internal-canary-only",
    }
    assert "five-seat CPU-serving workshop" in evidence["not_certified"]
    assert "three-workshop September 17 pilot" in evidence["not_certified"]
    assert evidence["contains_plaintext_credentials"] is False
    assert all(
        row["red"] and row["green_local"] and row["green_live"]
        for row in evidence["red_green_matrix"]
    )


def test_arena_cpu_serving_one_seat_evidence_checksum_matches():
    expected = CHECKSUM.read_text().split()[0]
    actual = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
    assert actual == expected
