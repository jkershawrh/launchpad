from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/catalog-intake-durability/green-integration.json"


def test_catalog_intake_durability_evidence_preserves_draft_boundary():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema"] == (
        "launchpad.redhat.com/catalog-intake-durability-evidence/v1"
    )
    assert evidence["result"] == "GREEN-integration"
    assert evidence["requirements"] == ["LP-T096", "LP-T101"]
    assert evidence["red"]["observed"] is True
    assert evidence["green_local"]["result"] == "pass"
    assert evidence["green_integration"]["tests"] == 4
    assert evidence["green_integration"]["database_retained"] is False
    assert evidence["contract"]["ha_requires_postgres"] is True
    assert evidence["contract"]["non_local_requires_postgres"] is True
    assert evidence["contract"]["live_catalog_dependency"] is False
    assert evidence["contract"]["stored_state"] == "draft"
    assert evidence["contract"]["promotion_actions"] is False
    assert all(value is False for value in evidence["mutations"].values())
    assert evidence["release"]["eligible"] is False


def test_catalog_intake_durability_evidence_checksum_is_valid():
    expected = EVIDENCE.with_suffix(".json.sha256").read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
