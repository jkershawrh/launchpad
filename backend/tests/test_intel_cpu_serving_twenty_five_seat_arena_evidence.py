import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/intel-llm-cpu-serving-25-seat-arena-20260908.json"
)


def _proof() -> dict:
    return json.loads(EVIDENCE.read_text())


def test_cpu_serving_twenty_five_seat_proof_is_complete_and_green():
    proof = _proof()

    assert proof["result"] == "GREEN-live-internal-25-seat"
    assert proof["workshop"]["seats_requested"] == 25
    assert proof["workshop"]["seats_ready"] == 25
    assert proof["workshop"]["validation_failures"] == 0
    assert len(proof["seat_results"]) == 25
    assert len({seat["namespace"] for seat in proof["seat_results"]}) == 25
    assert all(seat["passed"] for seat in proof["seat_results"])
    assert all(seat["showroom_http"] == 200 for seat in proof["seat_results"])
    assert all(seat["runtime_contract"] for seat in proof["seat_results"])
    assert all(seat["model_call"] for seat in proof["seat_results"])
    assert {seat["response_model"] for seat in proof["seat_results"]} == {
        "granite-2b-cpu"
    }

    cleanup = proof["cleanup"]
    assert cleanup["workshop_status"] == "completed"
    assert cleanup["seats_reclaimed"] == 25
    assert cleanup["failed_reclaims"] == 0
    assert cleanup["namespace_residue"] == 0
    assert cleanup["argocd_application_residue"] == 0
    assert cleanup["unrelated_public_cert_namespace_preserved"] is True


def test_cpu_serving_proof_does_not_overclaim_public_or_ha_certification():
    boundary = _proof()["certification_boundary"]

    assert boundary["public_access"] == "not certified"
    assert boundary["browser_trusted_arena_tls"] == "not certified"
    assert boundary["anythingllm_all_seats"] == "not exercised"
    assert boundary["lifecycle_ha"] == "not certified"
    assert boundary["node_ha"] == "not certified; only one worker schedulable"
    assert boundary["dr_failover"] == "not certified"
