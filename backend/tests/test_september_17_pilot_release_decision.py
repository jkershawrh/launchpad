"""Contract for the September 17 supervised internal-pilot decision."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = (
    ROOT / "evidence/runs/september-17-pilot-release-decision-20260909.json"
)


def test_release_decision_requires_repeatable_function_soak_and_cleanup_proof():
    evidence = json.loads(DECISION.read_text())

    assert evidence["schema"] == (
        "launchpad.redhat.com/september-17-pilot-release-decision/v2"
    )
    assert evidence["decision"] == "CONDITIONAL-GO-supervised-internal-pilot"
    assert evidence["automated_internal_pilot_gate"] == "GREEN-live"
    assert evidence["production_or_ga_decision"] == "NO-GO"
    assert evidence["contains_plaintext_credentials"] is False

    repeatability = evidence["repeatability"]
    assert repeatability["successful_exact_functional_runs"] == 3
    assert repeatability["latest_participants_started"] == 75
    assert repeatability["latest_participants_passed"] == 75
    assert repeatability["latest_router_restart_increase"] == 0

    soak = evidence["soak"]
    assert soak["result"] == "GREEN-live"
    assert soak["duration_observed_seconds"] >= 3600
    assert soak["failed_samples"] == 0
    assert soak["showrooms_available_per_sample"] == 75
    assert soak["restart_increase"] == 0

    cleanup = evidence["cleanup"]
    assert cleanup["latest_seat_records_reclaimed"] == 75
    assert cleanup["latest_failed_reclaims"] == 0
    for field in (
        "latest_remaining_namespaces",
        "latest_remaining_routes",
        "latest_remaining_rolebindings",
        "latest_remaining_argocd_applications",
    ):
        assert cleanup[field] == 0


def test_release_decision_does_not_overclaim_manual_public_or_ga_readiness():
    evidence = json.loads(DECISION.read_text())
    matrix = {row["gate"]: row["state"] for row in evidence["red_green_matrix"]}

    assert evidence["manual_frontend_acceptance"] == "PENDING"
    assert evidence["public_access"] == "DEFERRED-separate-certification-stream"
    assert matrix["manual requester and participant frontend"] == "RED-pending-manual"
    assert matrix["per-seat LiteLLM attribution"] == "RED-pending"
    assert matrix["dependency security triage"] == "RED-pending"
    assert matrix["public browser and SSO"] == "DEFERRED"
    assert evidence["rubric"]["automated_internal_pilot_score"] == 100
    assert evidence["rubric"]["production_or_ga_override"] is True
    assert evidence["rubric"]["production_or_ga_blockers"]


def test_release_decision_checksum_is_immutable():
    checksum = Path(f"{DECISION}.sha256")
    expected = checksum.read_text().split()[0]

    assert hashlib.sha256(DECISION.read_bytes()).hexdigest() == expected
