from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evidence/runs/catalog-intake-discovery-worker/manifest.json"


def test_discovery_worker_evidence_is_green_local_and_release_blocked() -> None:
    evidence = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert evidence["green"]["result"] == "16 passed"
    assert evidence["release_eligible"] is False
    assert evidence["non_claims"]
    assert all(value is False for value in evidence["mutations"].values())


def test_discovery_worker_evidence_hashes_match() -> None:
    evidence = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for name in ("red", "green", "contract", "containerfile"):
        item = evidence[name]
        artifact = ROOT / item["artifact"]
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == item["sha256"]
