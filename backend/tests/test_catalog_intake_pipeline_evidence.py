from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evidence/runs/catalog-intake-pipeline/manifest.json"


def test_catalog_intake_pipeline_evidence_is_green_but_not_release_eligible() -> None:
    evidence = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert evidence["result"] == "GREEN-local"
    assert evidence["test"]["result"] == "7 passed"
    assert evidence["release_eligible"] is False
    assert all(value is False for value in evidence["mutations"].values())


def test_catalog_intake_pipeline_evidence_hashes_match() -> None:
    evidence = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for item in (evidence["test"], evidence["contract"]):
        artifact = ROOT / item["artifact"]
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == item["sha256"]
