"""Contract for the Sep 17 two-cluster retained-workshop calibration run."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/september-17-two-cluster-calibration-2026-09-07.json"
CHECKSUM = Path(f"{EVIDENCE}.sha256")


def test_two_cluster_calibration_records_green_workshops_and_open_gate():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema"] == (
        "launchpad.redhat.com/september-17-two-cluster-calibration/v1"
    )
    assert evidence["release_status"] == "RED-live-infrastructure-blocked"
    assert evidence["clusters"] == {
        "building-an-ai-agent": "brutus",
        "multi-agent": "arena",
        "serve-llms": "arena",
    }

    agent = evidence["workshops"]["building-an-ai-agent"]
    assert agent["seat_count"] == 25
    assert agent["ready_seats"] == 25
    assert agent["post_soak_functional"]["passed"] == 25
    assert agent["post_soak_functional"]["failed"] == 0
    assert agent["post_soak_functional"]["isolation_passed"] is True

    multi = evidence["workshops"]["multi-agent"]
    assert multi["seat_count"] == 25
    assert multi["ready_seats"] == 25
    assert multi["functional"]["passed"] == 25
    assert multi["functional"]["failed"] == 0
    assert multi["functional"]["learner_policy_roundtrip_passed"] is True
    assert multi["functional"]["isolation_passed"] is True
    assert multi["functional"]["sensitive_values_absent"] is True

    failed = evidence["workshops"]["serve-llms-red-attempt"]
    assert failed["ready_seats"] == 22
    assert failed["failed_seats"] == 3
    assert failed["reclaimed_seats"] == 25
    assert failed["cleanup_residue"] == 0

    tuning = evidence["shared_model_calibration"]
    assert tuning["baseline"]["qos_class"] == "Guaranteed"
    assert tuning["rejected_48_96"]["qos_class"] == "Burstable"
    assert tuning["proposed_80_80"]["qos_class"] == "Guaranteed"
    assert tuning["proposed_80_80"]["live_deployed"] is False
    assert tuning["proposed_80_80"]["capacity_preview_can_provision"] is True
    assert tuning["proposed_80_80"]["capacity_preview_seats"] == 25

    assert evidence["blocking_gate"]["id"] == "arena-api-connectivity"
    assert evidence["blocking_gate"]["exact_trio_ordered"] is False
    assert evidence["rubric"]["score"] < evidence["rubric"]["required"]


def test_two_cluster_calibration_evidence_is_hashed_and_secret_safe():
    raw = EVIDENCE.read_bytes()
    expected = CHECKSUM.read_text().split()[0]

    assert hashlib.sha256(raw).hexdigest() == expected
    text = raw.decode()
    for forbidden in (
        "kubeadmin",
        "BEGIN " + "PRIVATE" + " KEY",
        "MAAS_API_KEY\"",
        "MODEL_API_KEY\"",
        "AGENT_AUTH_TOKEN\"",
        "sk-launchpad-",
    ):
        assert forbidden not in text
