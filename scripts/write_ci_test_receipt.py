"""Summarize the exact CI unit-test run without rerunning it or inventing a pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def _summary(junit: Path) -> tuple[dict[str, int] | None, str | None]:
    if not junit.is_file():
        return None, "junit-missing"
    try:
        root = ET.parse(junit).getroot()
        if root.tag == "testsuite":
            suites = [root]
        elif root.tag == "testsuites":
            suites = root.findall("testsuite")
        else:
            return None, "junit-invalid-root"
        if not suites:
            return None, "junit-empty"
        total = sum(int(suite.attrib["tests"]) for suite in suites)
        failures = sum(int(suite.attrib["failures"]) for suite in suites)
        errors = sum(int(suite.attrib["errors"]) for suite in suites)
        skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in suites)
        passed = total - failures - errors - skipped
        if (
            total < 1
            or min(passed, failures, errors, skipped) < 0
            or (passed == 0 and failures == 0 and errors == 0)
        ):
            return None, "junit-invalid-counts"
        return {
            "total": total,
            "passed": passed,
            "failed": failures + errors,
            "errors": errors,
            "skipped": skipped,
        }, None
    except (ET.ParseError, KeyError, ValueError, OSError):
        return None, "junit-invalid"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--step-outcome", choices=("success", "failure", "cancelled", "skipped"), required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()

    summary, error_code = _summary(args.junit)
    status = (
        "missing-evidence" if summary is None
        else "passed" if args.step_outcome == "success" and summary["failed"] == 0
        else "failed"
    )
    receipt = {
        "schema_version": "launchpad.redhat.com/ci-test-receipt/v1",
        "test_run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": "ci",
        "launchpad_commit": args.commit,
        "trigger": args.trigger,
        "branch": args.branch,
        "step_outcome": args.step_outcome,
        "status": status,
        "summary": summary,
        "junit_sha256": hashlib.sha256(args.junit.read_bytes()).hexdigest()
        if args.junit.is_file() else None,
        "error_code": error_code,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"CI test receipt: {status} ({summary['total'] if summary else 'unknown'} tests)")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
