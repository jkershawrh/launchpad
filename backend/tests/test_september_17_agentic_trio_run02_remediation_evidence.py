"""Proof that run-02 fixes are live without reclassifying the failed run."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/september-17-agentic-trio-run02-remediation-2026-09-06.json"
)
CHECKSUM = EVIDENCE.with_suffix(".json.sha256")


def test_run02_remediation_is_live_but_event_is_not_certified():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema"] == "launchpad.redhat.com/remediation-verification/v1"
    assert evidence["cluster_id"] == "arena"
    assert evidence["gitops"] == {
        "application": "launchpad-arena",
        "sync": "Synced",
        "health": "Healthy",
        "operation": "Succeeded",
    }
    assert evidence["backend_runtime"]["rollout_strategy"] == "Recreate"
    assert evidence["backend_runtime"]["memory_limit"] == "2Gi"
    assert evidence["detailed_health"]["overall"] == "ok"
    assert evidence["reconciler"]["database_reachable"] is True
    assert evidence["reconciler"]["errors"] == []
    assert evidence["run02_residue"]["remaining_namespaces"] == 0
    assert evidence["run02_residue"]["remaining_argocd_applications"] == 0
    assert evidence["run02_status_after_remediation"] == "RED"
    assert evidence["remediation_status"] == "GREEN-live"
    assert evidence["release_decision"] == "not-certified-until-run03"


def test_run02_remediation_evidence_is_hash_verified():
    expected = CHECKSUM.read_text().split()[0]
    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
