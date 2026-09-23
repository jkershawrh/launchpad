#!/usr/bin/env python3
"""Check an exact, local draft-image exception; never authorize publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.catalog_intake_candidate_policy import review_candidate_admission


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
    if pull_error or render_error:
        findings = []
        if pull_error:
            findings.append("pull-evidence-reference-invalid")
        if render_error:
            findings.append("render-evidence-reference-invalid")
        report = {"status": "RED", "findings": findings, "release_eligible": False}
    else:
        report = review_candidate_admission(policy, intake, pull_evidence, render_review)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "GREEN-local-candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
