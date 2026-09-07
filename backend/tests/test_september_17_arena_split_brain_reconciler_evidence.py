"""Contract for the Arena split-brain reconciler RED evidence."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/september-17-arena-split-brain-reconciler-20260907-red.json"
)


def test_split_brain_reconciler_evidence_identifies_and_contains_the_actor():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "RED-live-split-brain-reconciler"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["contains_plaintext_credentials"] is False

    actor = evidence["audit_finding"]["actor"]
    assert actor["username"].endswith(":launchpad-provisioner")
    assert actor["pod_bound_identity"] is False
    assert actor["deployed_arena_backend_identity"] is False
    assert evidence["audit_finding"]["orphan_cleanup_sweep_detected"] is True
    assert evidence["audit_finding"]["affected_catalog_families"] == [
        "intel-llm-cpu-serving",
        "multi-agent-quickstart",
    ]

    containment = evidence["live_containment"]
    assert containment["current_workloads_using_legacy_identity"] == 0
    assert containment["cluster_role_binding_deleted"] is True
    assert containment["service_account_deleted"] is True
    assert containment["namespace_delete_allowed_after_revocation"] is False

    guard = evidence["code_guard"]
    assert guard["requires_database"] is True
    assert guard["requires_control_plane_identity"] is True
    assert guard["namespace_selector_is_control_plane_scoped"] is True
    assert guard["full_non_local_tests"] == {
        "passed": 1182,
        "deselected": 13,
    }

    assert evidence["deployment"]["status"] == "blocked-vpn-route"
    assert evidence["release_gate"] == "failed"


def test_split_brain_reconciler_evidence_checksum_is_immutable():
    expected = Path(f"{EVIDENCE}.sha256").read_text().split()[0]
    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
