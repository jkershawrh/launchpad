"""Offline, fail-closed prerequisite gate for a candidate Launchpad control-plane home.

This validates submitted evidence references. It never connects to a cluster and
never authorizes migration, writer promotion, edge cutover, or rollback.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath

REQUIRED_CATEGORIES = (
    "hardware",
    "failure_domains",
    "openshift",
    "storage",
    "registry",
    "dns_tls",
    "ingress_egress",
    "identity",
    "secrets",
    "backup_restore",
    "observability",
    "ownership_support",
    "execution_connectivity",
)
SCHEMA = "launchpad.redhat.com/permanent-home-intake/v1"


def _evidence_ok(value: object, base_dir: Path) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    ref = PurePosixPath(value)
    if ref.is_absolute() or ".." in ref.parts or ":" in value or "?" in value:
        return False
    if not value.startswith("evidence/") or ref.suffix not in {".json", ".txt", ".xml", ".md"}:
        return False
    base = base_dir.resolve()
    path = (base / value).resolve()
    return path.is_relative_to(base) and path.is_file()


def evaluate(intake: object, base_dir: Path) -> dict:
    """Return only pass/fail identifiers; never echo submitted values or secrets."""
    failed = []
    if not isinstance(intake, dict) or intake.get("schema") != SCHEMA:
        return {
            "schema": SCHEMA,
            "ready_for_bootstrap": False,
            "authorizes_cutover": False,
            "failed_checks": ["schema"],
        }

    if set(intake) != {"schema", "target_id", "release_digest", "checks", "decision"}:
        failed.append("unexpected_fields")

    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", str(intake.get("target_id", ""))):
        failed.append("target_id")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(intake.get("release_digest", ""))):
        failed.append("immutable_release")

    checks = intake.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    if set(checks) - set(REQUIRED_CATEGORIES):
        failed.append("unknown_checks")
    for category in REQUIRED_CATEGORIES:
        item = checks.get(category)
        if not isinstance(item, dict):
            failed.append(category)
            continue
        evidence = item.get("evidence")
        if (
            set(item) != {"status", "owner", "evidence"}
            or item.get("status") != "pass"
            or not isinstance(item.get("owner"), str)
            or not item["owner"].strip()
            or not isinstance(evidence, list)
            or not evidence
            or not all(_evidence_ok(ref, base_dir) for ref in evidence)
        ):
            failed.append(category)

    decision = intake.get("decision")
    if (
        not isinstance(decision, dict)
        or not isinstance(decision.get("approved_by"), str)
        or not decision["approved_by"].strip()
    ):
        failed.append("signoff")
    if (
        not isinstance(decision, dict)
        or set(decision) != {"approved_by", "accepted_gaps"}
        or decision.get("accepted_gaps") != []
    ):
        failed.append("accepted_gaps")

    return {
        "schema": SCHEMA,
        "ready_for_bootstrap": not failed,
        "authorizes_cutover": False,
        "failed_checks": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intake", type=Path, help="candidate intake JSON")
    args = parser.parse_args()
    try:
        intake = json.loads(args.intake.read_text())
    except (OSError, json.JSONDecodeError):
        intake = None
    result = evaluate(intake, args.intake.parent)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready_for_bootstrap"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
