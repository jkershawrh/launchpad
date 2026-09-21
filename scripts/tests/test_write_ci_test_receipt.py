from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/write_ci_test_receipt.py"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def _run(tmp_path: Path, xml: str | None, outcome: str = "success"):
    junit = tmp_path / "unit-tests.xml"
    if xml is not None:
        junit.write_text(xml)
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--junit", str(junit),
            "--output", str(output),
            "--step-outcome", outcome,
            "--commit", "a" * 40,
            "--trigger", "pull_request",
            "--branch", "example",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, json.loads(output.read_text()) if output.exists() else None


def test_receipt_reports_only_the_actual_passing_run(tmp_path):
    result, receipt = _run(
        tmp_path,
        '<testsuites><testsuite tests="4" failures="0" errors="0" skipped="1"/></testsuites>',
    )

    assert result.returncode == 0
    assert receipt["status"] == "passed"
    assert receipt["summary"] == {
        "total": 4, "passed": 3, "failed": 0, "errors": 0, "skipped": 1
    }
    assert receipt["launchpad_commit"] == "a" * 40


def test_failed_step_cannot_be_reported_green_even_with_passing_xml(tmp_path):
    result, receipt = _run(
        tmp_path,
        '<testsuite tests="2" failures="0" errors="0" skipped="0"/>',
        outcome="failure",
    )

    assert result.returncode != 0
    assert receipt["status"] == "failed"


def test_missing_xml_is_not_a_zero_failure_pass(tmp_path):
    result, receipt = _run(tmp_path, None)

    assert result.returncode != 0
    assert receipt["status"] == "missing-evidence"
    assert receipt["summary"] is None


def test_all_skipped_run_is_not_green(tmp_path):
    result, receipt = _run(
        tmp_path,
        '<testsuite tests="2" failures="0" errors="0" skipped="2"/>',
    )

    assert result.returncode != 0
    assert receipt["status"] == "missing-evidence"


def test_junit_failure_and_collection_error_are_counted(tmp_path):
    result, receipt = _run(
        tmp_path,
        '<testsuites><testsuite tests="3" failures="1" errors="1" skipped="0"/></testsuites>',
    )

    assert result.returncode != 0
    assert receipt["status"] == "failed"
    assert receipt["summary"]["failed"] == 2
    assert receipt["summary"]["passed"] == 1


def test_collection_errors_without_passes_are_failed_not_missing(tmp_path):
    result, receipt = _run(
        tmp_path,
        '<testsuite tests="2" failures="0" errors="2" skipped="0"/>',
        outcome="failure",
    )

    assert result.returncode != 0
    assert receipt["status"] == "failed"
    assert receipt["summary"]["errors"] == 2


def test_ci_receipt_uses_unit_test_junit_instead_of_rerunning_tests():
    workflow = WORKFLOW.read_text()
    unit_tests = workflow.split("      - name: Unit tests", 1)[1].split(
        "      - name: Save test receipt", 1
    )[0]
    receipt = workflow.split("      - name: Save test receipt", 1)[1].split(
        "      - name: Upload receipt", 1
    )[0]

    assert '--junitxml="${{ runner.temp }}/backend-unit-tests.xml"' in unit_tests
    assert "scripts/write_ci_test_receipt.py" in receipt
    assert "backend-unit-tests.xml" in receipt
    assert "pytest" not in receipt
    assert '"$GITHUB_REF_NAME"' in receipt
    assert "test_write_ci_test_receipt.py" in workflow
