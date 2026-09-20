from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT / "evidence/runs/catalog-intake-draft-generation/green-local.json"
)


def test_catalog_draft_generation_evidence_preserves_non_live_boundary():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema"] == (
        "launchpad.redhat.com/catalog-intake-draft-evidence/v1"
    )
    assert evidence["result"] == "GREEN-local"
    assert evidence["requirements"] == ["LP-T098", "LP-T099"]
    assert evidence["red"]["observed"] is True
    assert evidence["green"]["result"] == "pass"
    assert evidence["contracts"] == {
        "receipt_schema": "launchpad.redhat.com/catalog-discovery-receipt/v1",
        "catalog_status": "draft",
        "exposure_policy": ["internal"],
        "maximum_seats": 1,
        "activation_blockers_required": True,
        "deterministic_output": True,
        "secret_payloads_copied": False,
    }
    assert all(value is False for value in evidence["mutations"].values())
    assert evidence["release"]["eligible"] is False


def test_catalog_draft_generation_evidence_checksum_is_valid():
    expected = EVIDENCE.with_suffix(".json.sha256").read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
