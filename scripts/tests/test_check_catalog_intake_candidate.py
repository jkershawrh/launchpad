from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
from pathlib import Path

from app.services.catalog_intake_render_attestation import (
    canonical_render_attestation_payload,
)

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


def test_authenticated_render_evidence_binds_exact_review_hash() -> None:
    module = _module()
    key = b"local-test-render-key-not-for-production"
    policy = {
        "catalog_item_id": "fraud",
        "source_revision": "a" * 40,
        "trusted_render_producer_id": "catalog-renderer-ci",
        "render_evidence": {"path": "review.json", "sha256": "b" * 64},
    }
    intake = {
        "runtime": {
            "workload": {
                "runtime_secret_name": "fraud-model-runtime",
                "helm_values": {
                    "app": {"image": "ghcr.io/example/fraud@sha256:" + "c" * 64},
                    "model": {"endpointFromSecret": True},
                },
            }
        }
    }
    review = {
        "manifest_sha256": "sha256:" + "d" * 64,
        "renderer_image_digest": "sha256:" + "e" * 64,
    }
    expected_values = module.candidate_helm_values_sha256(intake)
    envelope = {
        "schema_version": "launchpad.redhat.com/catalog-intake-render-attestation/v1",
        "producer_id": "catalog-renderer-ci",
        "observed_at": "2026-09-22T18:00:00+00:00",
        "catalog_item_id": "fraud",
        "source_revision": "a" * 40,
        "helm_values_sha256": expected_values,
        "manifest_sha256": review["manifest_sha256"],
        "renderer_image_digest": review["renderer_image_digest"],
        "render_review_sha256": "sha256:" + "b" * 64,
        "network_egress_denied": True,
        "workspace_removed": True,
    }
    envelope["mac"] = hmac.new(
        key,
        canonical_render_attestation_payload(envelope),
        hashlib.sha256,
    ).hexdigest()

    result = module.authenticate_render_evidence(policy, intake, review, envelope, key)
    assert result["status"] == "GREEN-local-authenticated"
    assert result["authenticated"] is True

    envelope["render_review_sha256"] = "sha256:" + "f" * 64
    result = module.authenticate_render_evidence(policy, intake, review, envelope, key)
    assert result["status"] == "RED"
    assert "attestation-binding-mismatch" in result["findings"]
