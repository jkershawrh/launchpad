from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/catalog-intake-submission/green-local.json"


def test_catalog_intake_submission_evidence_is_local_and_fail_closed():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema"] == (
        "launchpad.redhat.com/catalog-intake-submission-evidence/v1"
    )
    assert evidence["result"] == "GREEN-local"
    assert evidence["requirements"] == ["LP-T096", "LP-T101"]
    assert evidence["red"]["observed"] is True
    assert evidence["green"] == {
        "tests": 16,
        "command": "PYTHONPATH=.:backend ./.venv/bin/pytest -q backend/tests/test_catalog_intake_submission.py backend/tests/test_catalog_intake_api.py",
        "result": "pass",
    }
    assert evidence["contract"]["state"] == "draft"
    assert evidence["contract"]["orderable"] is False
    assert evidence["contract"]["promotion_eligible"] is False
    assert evidence["contract"]["supported_targets"] == []
    assert evidence["contract"]["storage_scope"] == "process-local-draft"
    assert all(value is False for value in evidence["mutations"].values())
    assert evidence["release"]["eligible"] is False


def test_catalog_intake_submission_evidence_checksum_is_valid():
    expected = EVIDENCE.with_suffix(".json.sha256").read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
