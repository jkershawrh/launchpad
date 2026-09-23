from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_catalog_intake_candidate.py"


def _module():
    spec = importlib.util.spec_from_file_location("candidate_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hash_pinned_json_reference_is_loaded_without_echoing_content(tmp_path: Path) -> None:
    payload = {"status": "review-ready", "private_note": "do-not-echo"}
    evidence = tmp_path / "render-review.json"
    raw = json.dumps(payload).encode()
    evidence.write_bytes(raw)

    loaded, finding = _module().load_hash_pinned_json(
        {"path": evidence.name, "sha256": hashlib.sha256(raw).hexdigest()}, root=tmp_path
    )

    assert loaded == payload
    assert finding is None


def test_missing_invalid_or_tampered_reference_fails_closed(tmp_path: Path) -> None:
    evidence = tmp_path / "render-review.json"
    evidence.write_text('{"status":"review-ready"}')
    module = _module()

    for contract in (
        None,
        {},
        {"path": "../outside.json", "sha256": "0" * 64},
        {"path": evidence.name, "sha256": "0" * 64},
        {"path": evidence.name, "sha256": "invalid"},
    ):
        loaded, finding = module.load_hash_pinned_json(contract, root=tmp_path)
        assert loaded is None
        assert finding == "evidence-reference-invalid"
