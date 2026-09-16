import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/september-17-live-workshops-90-seat-workflow-20260916.json"
)
CHECKSUM = Path(f"{EVIDENCE}.sha256")


def test_all_three_live_workshops_passed_every_seat_workflow():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["scope"]["seats_tested"] == 90
    assert evidence["scope"]["participant_claims_consumed"] == 0
    assert len(evidence["results"]) == 3
    assert sum(item["seats_tested"] for item in evidence["results"]) == 90
    assert all(item["seats_passed"] == 30 for item in evidence["results"])
    assert all(item["seats_failed"] == 0 for item in evidence["results"])
    assert evidence["post_test_state"]["workshops_ready"] == 3
    assert evidence["post_test_state"]["seats_ready"] == 90
    assert evidence["post_test_state"]["contains_plaintext_credentials"] is False


def test_live_workflow_evidence_checksum_matches():
    expected, filename = CHECKSUM.read_text().strip().split("  ", maxsplit=1)

    assert filename == EVIDENCE.name
    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
