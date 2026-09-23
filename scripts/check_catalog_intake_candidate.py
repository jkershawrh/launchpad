#!/usr/bin/env python3
"""Check an exact, local draft-image exception; never authorize publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.catalog_intake_candidate_policy import (
    candidate_helm_values_sha256,
    review_candidate_admission,
)
from app.services.catalog_intake_render_attestation import verify_render_attestation


def load_hash_pinned_json(contract: object, *, root: Path = ROOT) -> tuple[dict | None, str | None]:
    """Load repository-scoped evidence only when its exact bytes are pinned."""

    if not isinstance(contract, dict):
        return None, "evidence-reference-invalid"
    path_value = contract.get("path")
    expected_hash = contract.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected_hash, str):
        return None, "evidence-reference-invalid"
    root = root.resolve()
    evidence_path = (root / path_value).resolve()
    if (
        not evidence_path.is_relative_to(root)
        or not evidence_path.is_file()
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
    ):
        return None, "evidence-reference-invalid"
    raw = evidence_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        return None, "evidence-reference-invalid"
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "evidence-reference-invalid"
    if not isinstance(value, dict):
        return None, "evidence-reference-invalid"
    return value, None


def authenticate_render_evidence(
    policy: dict,
    intake: dict,
    render_review: dict | None,
    envelope: dict | None,
    producer_key: bytes | None,
) -> dict:
    """Authenticate exact render evidence without exposing external key material."""

    render_reference = policy.get("render_evidence")
    review_hash = render_reference.get("sha256") if isinstance(render_reference, dict) else None
    expected = {
        "catalog_item_id": policy.get("catalog_item_id"),
        "source_revision": policy.get("source_revision"),
        "helm_values_sha256": candidate_helm_values_sha256(intake),
        "manifest_sha256": render_review.get("manifest_sha256")
        if isinstance(render_review, dict)
        else None,
        "renderer_image_digest": render_review.get("renderer_image_digest")
        if isinstance(render_review, dict)
        else None,
        "render_review_sha256": "sha256:" + review_hash if isinstance(review_hash, str) else None,
    }
    producer_id = policy.get("trusted_render_producer_id")
    producers = (
        {producer_id: producer_key}
        if isinstance(producer_id, str) and isinstance(producer_key, bytes)
        else {}
    )
    return verify_render_attestation(envelope, expected=expected, trusted_producers=producers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="config/catalog-intake-candidate-policy.yaml")
    parser.add_argument("--intake", default="catalog-onboarding/hybrid-fraud-detection.yaml")
    args = parser.parse_args()
    policy_path = (ROOT / args.policy).resolve()
    intake_path = (ROOT / args.intake).resolve()
    if not policy_path.is_relative_to(ROOT) or not intake_path.is_relative_to(ROOT):
        parser.error("policy and intake must be inside this repository")
    policy = yaml.safe_load(policy_path.read_text())
    intake = yaml.safe_load(intake_path.read_text())
    pull_evidence, pull_error = load_hash_pinned_json(policy.get("pull_evidence"))
    render_review, render_error = load_hash_pinned_json(policy.get("render_evidence"))
    render_envelope, attestation_error = load_hash_pinned_json(policy.get("render_attestation"))
    if pull_error or render_error or attestation_error:
        findings = []
        if pull_error:
            findings.append("pull-evidence-reference-invalid")
        if render_error:
            findings.append("render-evidence-reference-invalid")
        if attestation_error:
            findings.append("render-attestation-reference-invalid")
        report = {"status": "RED", "findings": findings, "release_eligible": False}
    else:
        key_value = os.environ.get("CATALOG_RENDER_ATTESTATION_KEY")
        attestation = authenticate_render_evidence(
            policy,
            intake,
            render_review,
            render_envelope,
            key_value.encode() if key_value else None,
        )
        report = review_candidate_admission(
            policy,
            intake,
            pull_evidence,
            render_review,
            attestation,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "GREEN-local-candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
