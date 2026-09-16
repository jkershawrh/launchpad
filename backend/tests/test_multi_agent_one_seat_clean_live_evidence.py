from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/multi-agent-one-seat-clean-live-2026-09-05.json"
CHECKSUM = ROOT / "evidence/multi-agent-one-seat-clean-live-2026-09-05.json.sha256"
ONBOARDING = ROOT / "catalog-onboarding/multi-agent-quickstart.yaml"


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text())


def test_clean_one_seat_reached_ready_without_retry_or_live_patch():
    evidence = _evidence()

    assert evidence["schema"] == "launchpad.redhat.com/multi-agent-live-seat-evidence/v1"
    assert evidence["result"] == "pass-internal-one-seat-clean-first-pass"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["order"]["seat_count"] == 1
    assert evidence["order"]["provisioning_attempts"] == 1
    assert evidence["order"]["retry_count"] == 0
    assert evidence["order"]["live_patch_count"] == 0
    assert evidence["checks"]["workload_health"]["ready_containers"] == 11
    assert evidence["checks"]["workload_health"]["container_restarts"] == 0
    assert evidence["checks"]["readiness"]["agents_discovered"] == 3


def test_clean_one_seat_proved_ai_journey_isolation_and_secret_boundary():
    evidence = _evidence()

    assert evidence["checks"]["multi_agent_journey"]["steps"] == 3
    assert evidence["checks"]["multi_agent_journey"]["mcp_steps"] == 3
    assert evidence["checks"]["multi_agent_journey"]["errors"] == 0
    assert evidence["checks"]["semantic_routing"]["status"] == "ok"
    assert evidence["checks"]["guardrails"]["blocked_steps"] == 3
    assert evidence["checks"]["terminal_scope"]["own_namespace_edit_allowed"] is True
    assert evidence["checks"]["terminal_scope"]["cross_namespace_read_denied"] is True
    assert evidence["checks"]["terminal_scope"]["node_list_denied"] is True
    assert evidence["checks"]["runtime_secret_boundary"]["secret_in_gitops"] is False
    assert evidence["checks"]["launchpad_validation"]["repeatability_score_after_reclaim"] == 100
    assert evidence["checks"]["launchpad_validation"]["repeatability_survives_backend_restart"] is True


def test_clean_one_seat_reclaim_left_zero_labeled_residue():
    evidence = _evidence()

    assert evidence["cleanup"] == {
        "status": "pass",
        "seconds": 63,
        "remaining_namespaces": 0,
        "remaining_applications": 0,
        "remaining_role_bindings": 0,
        "remaining_persistent_volume_claims": 0,
        "remaining_persistent_volumes": 0,
        "remaining_routes": 0,
        "remaining_secrets": 0,
        "session_status": "reclaimed",
        "model_key_cleared": True,
    }
    assert evidence["security"]["contains_plaintext_credentials"] is False
    assert evidence["security"]["credential_values_logged"] is False


def test_clean_one_seat_evidence_remains_valid_after_thirty_seat_promotion():
    evidence = _evidence()
    contract = yaml.safe_load(ONBOARDING.read_text())

    assert contract["certification"]["stage"] == "thirty-seat-certified"
    assert contract["certification"]["max_workshop_seats"] == 30
    assert evidence["release_boundary"] == {
        "internal_one_seat_functional_gate": True,
        "clean_first_pass": True,
        "internal_five_seat_gate": False,
        "internal_twenty_five_seat_gate": False,
        "public_access_certified": False,
        "general_availability": False,
    }


def test_clean_multi_agent_live_evidence_checksum_matches_artifact():
    expected, filename = CHECKSUM.read_text().strip().split("  ", maxsplit=1)

    assert filename == EVIDENCE.name
    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
