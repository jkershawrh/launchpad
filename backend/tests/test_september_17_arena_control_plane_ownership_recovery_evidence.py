import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/september-17-arena-control-plane-ownership-recovery-20260907.json"
)


def _evidence():
    return json.loads(EVIDENCE.read_text())


def test_arena_control_plane_ownership_recovery_is_green_live():
    evidence = _evidence()

    assert evidence["result"] == "GREEN-live"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["control_plane_id"] == "arena-primary"
    assert evidence["ownership_labels_observed_before_reconcile"][
        "launchpad.redhat.com/control-plane-id"
    ] == "arena-primary"
    assert evidence["reconciliation"] == {
        "sessions_reconciled": 0,
        "late_workshop_sessions_reclaimed": [],
        "orphan_namespaces_deleted": [],
        "errors": [],
        "active_namespace_survived": True,
    }


def test_arena_control_plane_ownership_recovery_left_zero_residue():
    cleanup = _evidence()["cleanup"]

    assert cleanup["workshop_status"] == "completed"
    assert cleanup["seat_status"] == "reclaimed"
    assert cleanup["session_status"] == "reclaimed"
    assert cleanup["remaining_workshop_namespaces"] == 0
    assert cleanup["remaining_session_namespaces"] == 0
    assert cleanup["remaining_workshop_argocd_applications"] == 0
    assert cleanup["credentials_scrubbed_event_recorded"] is True


def test_arena_recovery_keeps_service_account_model_minimal():
    boundary = _evidence()["service_account_boundary"]

    assert boundary["arena_runtime_identity"].endswith(":launchpad-backend")
    assert boundary["stale_remote_identity_revoked"].endswith(
        ":launchpad-provisioner"
    )
    assert boundary["per_seat_infrastructure_service_accounts_required"] is False
    assert boundary["per_workshop_infrastructure_service_accounts_required"] is False


def test_arena_recovery_does_not_promote_the_event_release_early():
    evidence = _evidence()

    assert all(row["green_live"] is True for row in evidence["red_green_matrix"])
    assert evidence["release_boundary"]["ownership_recovery_gate"] == "GREEN-live"
    assert evidence["release_boundary"]["september_17_three_workshop_release"] == "RED"
    assert len(evidence["release_boundary"]["remaining_gates"]) == 4
    assert evidence["contains_plaintext_credentials"] is False
