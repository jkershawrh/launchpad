"""Contract for the cleanup recovery after the retained Arena 25+25 RED run."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/september-17-arena-retained-25x2-20260907-cleanup-green.json"
)


def test_retained_25x2_cleanup_is_green_without_false_certification():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "GREEN-live-cleanup-only"
    assert evidence["cluster_ref"] == "arena"
    assert evidence["contains_plaintext_credentials"] is False

    for workshop in evidence["workshops"].values():
        assert workshop["status"] == "completed"
        assert workshop["seat_statuses"] == {"reclaimed": 25}
        assert workshop["error"] is None

    cleanup = evidence["cleanup_observation"]
    assert cleanup["active_session_count"] == 0
    assert cleanup["active_namespace_records"] == 0
    assert cleanup["live_managed_namespaces"] == 0
    assert cleanup["orphan_live_namespaces"] == []
    assert cleanup["missing_active_namespaces"] == []
    assert cleanup["generated_argocd_applications"] == 0

    matrix = {row["id"]: row for row in evidence["red_green_matrix"]}
    assert matrix["SEPT17-25X2-CLEANUP-001"]["status"] == "GREEN-live"
    assert matrix["SEPT17-25X2-PARTICIPANT-001"]["status"] == "RED-live"
    assert matrix["SEPT17-25X2-NODE-STABILITY-001"]["status"] == "RED-live"
    assert matrix["SEPT17-25X2-LIFECYCLE-001"]["status"] == "RED-live"

    assert evidence["rubric"]["score"] < evidence["rubric"]["required"]
    assert evidence["rubric"]["release_gate"] == "failed"
    assert evidence["remaining_blockers"]["namespace_deletion_initiator_confirmed"] is False


def test_retained_25x2_cleanup_evidence_checksum_is_immutable():
    checksum_file = Path(f"{EVIDENCE}.sha256")
    expected = checksum_file.read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
