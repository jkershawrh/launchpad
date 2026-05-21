#!/usr/bin/env python3
"""Generate a JSON test receipt from E2E test output.

Usage:
  ./live-e2e-test.sh 2>&1 | python3 scripts/generate-receipt.py local
  ./cluster-e2e-test.sh 2>&1 | python3 scripts/generate-receipt.py infra01
"""
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime


def parse_results(lines):
    tests = []
    current_step = None
    step_num = 0

    for line in lines:
        step_match = re.match(r"Step (\d+): (.+)", line)
        if step_match:
            step_num = int(step_match.group(1))
            current_step = step_match.group(2)

        pass_match = re.search(r"PASS: (.+)", line)
        if pass_match:
            tests.append({
                "step": step_num,
                "step_name": current_step,
                "name": pass_match.group(1),
                "status": "pass",
            })

        fail_match = re.search(r"FAIL: (.+)", line)
        if fail_match:
            tests.append({
                "step": step_num,
                "step_name": current_step,
                "name": fail_match.group(1),
                "status": "fail",
            })

        skip_match = re.search(r"SKIP: (.+)", line)
        if skip_match:
            tests.append({
                "step": step_num,
                "step_name": current_step,
                "name": skip_match.group(1),
                "status": "skip",
            })

    return tests


def get_git_info():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            text=True,
        ).strip()
        return commit
    except Exception:
        return "unknown"


def main():
    env = sys.argv[1] if len(sys.argv) > 1 else "local"
    lines = sys.stdin.read().splitlines()
    tests = parse_results(lines)

    passed = sum(1 for t in tests if t["status"] == "pass")
    failed = sum(1 for t in tests if t["status"] == "fail")
    skipped = sum(1 for t in tests if t["status"] == "skip")

    now = datetime.utcnow()
    receipt = {
        "test_run_id": str(uuid.uuid4()),
        "timestamp": now.isoformat() + "Z",
        "environment": env,
        "launchpad_commit": get_git_info(),
        "tests": tests,
        "summary": {
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
    }

    filename = f"test-receipts/{env}-{now.strftime('%Y-%m-%dT%H%M%S')}.json"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filepath = os.path.join(root, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\nReceipt saved: {filename}")
    print(f"  Environment: {env}")
    print(f"  Tests: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"  Commit: {receipt['launchpad_commit']}")


if __name__ == "__main__":
    main()
