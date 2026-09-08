import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/arena-lifecycle-process-ha-20260908.json"


def _proof() -> dict:
    return json.loads(EVIDENCE.read_text())


def test_arena_process_takeover_proof_is_complete_and_green():
    proof = _proof()

    assert proof["result"] == "GREEN-live-process-ha"
    assert proof["source"]["cluster_ref"] == "arena"
    assert "@sha256:" in proof["source"]["backend_image"]
    assert proof["topology"]["lifecycle_worker_processes_ready"] == 2
    assert proof["topology"]["readiness"] == {
        "status": "ready",
        "control_plane_role": "pass",
        "database": "pass",
        "lifecycle_schema": "pass",
    }

    provision = proof["provision_takeover"]
    assert provision["final_job_status"] == "succeeded"
    assert provision["final_fencing_token"] > provision["initial_fencing_token"]
    assert provision["target_cluster_preserved"] == "arena"
    assert provision["namespaces_created"] == 1
    assert provision["duplicate_namespaces"] == 0
    assert provision["showroom_http"] == 200
    assert provision["validation_failures"] == 0

    reclaim = proof["reclaim_takeover"]
    assert reclaim["final_job_status"] == "succeeded"
    assert reclaim["final_fencing_token"] > reclaim["initial_fencing_token"]
    assert reclaim["target_cluster_preserved"] == "arena"
    assert reclaim["last_error"] is None
    assert reclaim["session_status"] == "reclaimed"
    assert set(reclaim["residue"].values()) == {0}


def test_arena_process_takeover_proof_preserves_certification_boundaries():
    proof = _proof()
    boundary = proof["certification_boundary"]

    assert proof["public_certification_lab"]["preserved"] is True
    assert boundary["single_seat_process_takeover"] == (
        "certified for provision and reclaim"
    )
    assert boundary["node_ha"].startswith("not certified")
    assert boundary["workshop_ha_five_seat"] == "not certified"
    assert boundary["workshop_ha_twenty_five_seat"] == "not certified"
    assert boundary["clean_latency_run"].startswith("not certified")
    assert boundary["flightpath_dr"] == "not certified"
    assert boundary["stable_public_dns_tls"].startswith("not certified")
