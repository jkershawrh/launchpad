#!/usr/bin/env python3
"""Inventory sanitation candidates without recording matched values."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evidence" / "repository-sanitization" / "inventory-v1.json"
RHPDS_TERMS = re.compile(r"rhpds|agnosticv|agnosticd|opentlc|demo\.redhat\.com|SANDBOX_API_URL|SANDBOX_LOGIN_TOKEN|app\.adapters\.rhdp", re.I)
OPERATIONAL_DOMAIN = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:fm2aihpcsed\.com|smg-helix\.ai|trycloudflare\.com)\b", re.I)
PRIVATE_IP = re.compile(r"(?<![0-9.])(?:10\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.)\d{1,3}\.\d{1,3}(?![0-9.])")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", re.I)
FIXTURE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "example.test"}
GOVERNANCE_PATHS = {
    "contracts/repository-sanitization-v1.yaml",
    "docs/repository-hygiene.md",
    "scripts/audit_repository_sanitization.py",
    "scripts/tests/test_repository_sanitization.py",
    "backend/tests/test_runtime_mode_contract.py",
}


def tracked_files() -> list[str]:
    output = subprocess.check_output(("git", "ls-files", "-z"), cwd=ROOT, text=True)
    return sorted(path for path in output.split("\0") if path)


def _read_text(path: str) -> str | None:
    candidate = ROOT / path
    try:
        if candidate.stat().st_size > 2_000_000:
            return None
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def disposition(path: str, categories: set[str]) -> str:
    if path.startswith("backend/app/adapters/rhdp/"):
        return "remove-after-runtime-consumer-tests"
    if path.startswith("deploy/agnosticv/"):
        return "remove-after-deployment-consumer-tests"
    if path == "backend/tests/test_rhdp_adapters.py":
        return "remove-with-rhdp-adapter"
    if "runtime-rhdp-coupling" in categories:
        return "refactor-before-adapter-removal"
    if "personal-identifier" in categories:
        return "sanitize"
    if "operational-topology" in categories and path.startswith(("evidence/", "docs/")):
        return "replace-with-sanitized-summary"
    if "rhpds-artifact-provenance" in categories:
        return "retain-until-mirrored-and-certified"
    if "rhpds-reference" in categories:
        return "review-and-generalize"
    return "retain"


def audit() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    files = tracked_files()
    for path in files:
        if path in GOVERNANCE_PATHS or path.startswith("evidence/repository-sanitization/"):
            continue
        text = _read_text(path)
        if text is None:
            continue
        categories: set[str] = set()
        if RHPDS_TERMS.search(text) or path.startswith("deploy/agnosticv/"):
            categories.add("rhpds-reference")
        if path.startswith("backend/app/adapters/rhdp/") or "app.adapters.rhdp" in text or 'mode == "rhdp"' in text:
            categories.add("runtime-rhdp-coupling")
        if "github.com/rhpds/" in text or "quay.io/rhpds/" in text:
            categories.add("rhpds-artifact-provenance")
        domain_count = len(OPERATIONAL_DOMAIN.findall(text))
        private_ip_count = len(PRIVATE_IP.findall(text))
        if domain_count or private_ip_count:
            categories.add("operational-topology")
        non_fixture_email_count = sum(1 for match in EMAIL.finditer(text) if match.group(1).lower() not in FIXTURE_EMAIL_DOMAINS)
        if non_fixture_email_count:
            categories.add("personal-identifier")
        if categories:
            records.append({"path": path, "categories": sorted(categories), "disposition": disposition(path, categories), "counts": {"operational_domains": domain_count, "private_ips": private_ip_count, "non_fixture_emails": non_fixture_email_count}})
    category_counts = Counter(category for record in records for category in record["categories"])
    disposition_counts = Counter(record["disposition"] for record in records)
    return {
        "schema_version": "launchpad.redhat.com/v1alpha1",
        "kind": "RepositorySanitizationInventory",
        "metadata": {"contract": "contracts/repository-sanitization-v1.yaml", "privacy": "paths-and-counts-only-no-matched-values"},
        "summary": {"tracked_files_reviewed": len(files), "candidate_files": len(records), "categories": dict(sorted(category_counts.items())), "dispositions": dict(sorted(disposition_counts.items()))},
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-runtime-clean", action="store_true")
    args = parser.parse_args()
    report = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    blockers = [record for record in report["records"] if "runtime-rhdp-coupling" in record["categories"]]
    if args.check_runtime_clean and blockers:
        print(f"runtime sanitation blocked by {len(blockers)} tracked file(s)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
