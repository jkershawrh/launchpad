from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import yaml
from app.services.catalog_supply_chain import evaluate_artifact_release_evidence

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/artifact-registry-policy.yaml"


def _receipt() -> dict:
    digest = "a" * 64
    return {
        "schema_version": "launchpad.redhat.com/artifact-release-evidence/v1",
        "component": "backend",
        "source": {
            "repository": "https://github.com/jkershawrh/launchpad.git",
            "revision": "b" * 40,
            "tree_dirty": False,
        },
        "image": f"quay.io/redhat-gpte/launchpad-backend@sha256:{digest}",
        "architectures": ["amd64"],
        "build": {
            "builder_identity": "github-actions:jkershawrh/launchpad",
            "workflow_url": "https://github.com/jkershawrh/launchpad/actions/runs/1",
            "completed_at": "2026-09-21T06:00:00Z",
        },
        "checks": {
            "vulnerability_scan": {
                "status": "passed",
                "critical_findings": 0,
                "high_findings": 0,
                "evidence": ["evidence/vulnerability-scan.json"],
            },
            "sbom": {
                "status": "passed",
                "artifact": "oci://quay.io/redhat-gpte/launchpad-backend:sbom",
                "sha256": "c" * 64,
                "evidence": ["evidence/sbom.json"],
            },
            "signature": {
                "status": "passed",
                "identity": "github-actions:jkershawrh/launchpad",
                "subject_image": f"quay.io/redhat-gpte/launchpad-backend@sha256:{digest}",
                "verified": True,
                "evidence": ["evidence/signature.json"],
            },
            "provenance": {
                "status": "passed",
                "artifact": "oci://quay.io/redhat-gpte/launchpad-backend:provenance",
                "sha256": "d" * 64,
                "subject_image": f"quay.io/redhat-gpte/launchpad-backend@sha256:{digest}",
                "source_repository": "https://github.com/jkershawrh/launchpad.git",
                "source_revision": "b" * 40,
                "builder_identity": "github-actions:jkershawrh/launchpad",
                "verified": True,
                "evidence": ["evidence/provenance.json"],
            },
            "license_policy": {
                "status": "passed",
                "evidence": ["evidence/license-policy.json"],
            },
            "retention": {
                "status": "passed",
                "protected_until": "2027-09-21T06:00:00Z",
                "rollback_releases_retained": 3,
                "evidence": ["evidence/retention.json"],
            },
        },
    }


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "release-evidence.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def test_complete_release_evidence_is_locally_consistent(tmp_path: Path) -> None:
    report = evaluate_artifact_release_evidence(POLICY, _write(tmp_path, _receipt()))

    assert report["status"] == "GREEN-local"
    assert report["eligible"] is True
    assert report["failures"] == []
    assert report["component"] == "backend"


def test_release_evidence_rejects_wrong_repository_or_mutable_image(
    tmp_path: Path,
) -> None:
    receipt = _receipt()
    receipt["image"] = "quay.io/personal/launchpad-backend:latest"

    report = evaluate_artifact_release_evidence(POLICY, _write(tmp_path, receipt))

    assert report["eligible"] is False
    assert "image must use an immutable sha256 digest" in report["failures"]
    assert "image does not match the component repository" in report["failures"]


def test_release_evidence_rejects_dirty_or_unpinned_source(tmp_path: Path) -> None:
    receipt = _receipt()
    receipt["source"]["revision"] = "main"
    receipt["source"]["tree_dirty"] = True

    report = evaluate_artifact_release_evidence(POLICY, _write(tmp_path, receipt))

    assert report["eligible"] is False
    assert "source revision must be an immutable 40-character Git SHA" in report[
        "failures"
    ]
    assert "source tree must be clean" in report["failures"]


def test_release_evidence_rejects_missing_or_failed_proof(tmp_path: Path) -> None:
    receipt = _receipt()
    del receipt["checks"]["sbom"]
    receipt["checks"]["signature"]["verified"] = False
    receipt["checks"]["vulnerability_scan"]["high_findings"] = 1
    receipt["checks"]["license_policy"]["evidence"] = []

    report = evaluate_artifact_release_evidence(POLICY, _write(tmp_path, receipt))

    assert report["eligible"] is False
    assert "required release check is missing: sbom" in report["failures"]
    assert "signature verification did not pass" in report["failures"]
    assert "vulnerability scan contains high findings" in report["failures"]
    assert "release check has no evidence: license_policy" in report["failures"]


def test_release_evidence_rejects_proof_for_another_image_or_source(
    tmp_path: Path,
) -> None:
    receipt = _receipt()
    receipt["checks"]["signature"]["subject_image"] = (
        "quay.io/redhat-gpte/launchpad-backend@sha256:" + "e" * 64
    )
    provenance = receipt["checks"]["provenance"]
    provenance["subject_image"] = receipt["checks"]["signature"]["subject_image"]
    provenance["source_revision"] = "f" * 40
    provenance["builder_identity"] = "github-actions:untrusted/repository"

    report = evaluate_artifact_release_evidence(POLICY, _write(tmp_path, receipt))

    assert report["eligible"] is False
    assert "signature subject image does not match release image" in report["failures"]
    assert "provenance subject image does not match release image" in report["failures"]
    assert "provenance source revision does not match release source" in report["failures"]
    assert "provenance builder identity does not match release build" in report["failures"]


def test_release_evidence_rejects_missing_proof_bindings(tmp_path: Path) -> None:
    receipt = _receipt()
    del receipt["checks"]["signature"]["subject_image"]
    del receipt["checks"]["provenance"]["source_repository"]

    report = evaluate_artifact_release_evidence(POLICY, _write(tmp_path, receipt))

    assert report["eligible"] is False
    assert "signature subject image does not match release image" in report["failures"]
    assert "provenance source repository does not match release source" in report["failures"]


def test_release_evidence_rejects_inline_credentials_and_weak_retention(
    tmp_path: Path,
) -> None:
    receipt = deepcopy(_receipt())
    receipt["build"]["token"] = "must-not-be-recorded"
    receipt["checks"]["retention"]["rollback_releases_retained"] = 2

    report = evaluate_artifact_release_evidence(POLICY, _write(tmp_path, receipt))

    assert report["eligible"] is False
    assert any("inline credential field" in item for item in report["failures"])
    assert "retention proof preserves fewer releases than policy" in report["failures"]


def test_release_evidence_cli_emits_machine_readable_gate(tmp_path: Path) -> None:
    receipt = _write(tmp_path, _receipt())
    output = tmp_path / "report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validate_artifact_release.py"),
            "--policy",
            str(POLICY),
            "--receipt",
            str(receipt),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = yaml.safe_load(output.read_text())
    assert payload["eligible"] is True
    assert payload["status"] == "GREEN-local"
