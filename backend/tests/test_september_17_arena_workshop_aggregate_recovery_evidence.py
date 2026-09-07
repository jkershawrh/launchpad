import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/september-17-arena-workshop-aggregate-recovery-20260907.json"
)


def _evidence():
    return json.loads(EVIDENCE.read_text())


def test_arena_workshop_aggregate_recovery_is_green_live():
    evidence = _evidence()
    proof = evidence["live_proof"]

    assert evidence["result"] == "GREEN-live"
    assert proof["workshop_status_after_individual_session_reclaim"] == "ready"
    assert proof["session_status_before_reconcile"] == "reclaimed"
    assert proof["workshop_status_after_reconcile"] == "completed"
    assert proof["seat_status_after_reconcile"] == "reclaimed"
    assert proof["reconciler_response"]["errors"] == []
    assert proof["reconciler_response"]["workshops_reconciled"] == [
        {
            "workshop_id": proof["workshop_id"],
            "cluster_id": "arena",
            "session_count": 1,
        }
    ]


def test_arena_workshop_aggregate_recovery_left_zero_residue():
    proof = _evidence()["live_proof"]

    assert proof["remaining_namespaces"] == 0
    assert proof["remaining_argocd_applications"] == 0


def test_arena_workshop_aggregate_recovery_preserves_fail_closed_release():
    evidence = _evidence()

    assert evidence["historical_records_repaired"] == {
        "workshops": 3,
        "seats": 5,
        "live_namespaces_before_repair": 0,
        "final_workshop_status": "completed",
    }
    assert evidence["behavior_contract"][
        "leave_workshop_nonterminal_when_any_session_is_active"
    ] is True
    assert evidence["test_results"]["related_suite_passed"] == 95
    assert evidence["release_boundary"]["workshop_aggregate_recovery_gate"] == (
        "GREEN-live"
    )
    assert evidence["release_boundary"]["september_17_three_workshop_release"] == (
        "RED"
    )
    assert evidence["contains_plaintext_credentials"] is False
