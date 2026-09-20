from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import yaml
from app.services.catalog_supply_chain import (
    build_registry_policy_report,
    evaluate_destination_qualification,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/artifact-registry-policy.yaml"


def test_registry_contract_is_complete_but_fails_closed_for_release() -> None:
    report = build_registry_policy_report(POLICY)

    assert report["contract_status"] == "GREEN-local"
    assert report["release_eligible"] is False
    assert report["authority"]["origin"] == "quay.io/redhat-gpte"
    assert report["repositories"]["keycloak"] != report["repositories"]["backend"]
    assert report["contract_violations"] == []
    assert "organization ownership approval is not recorded" in report["release_gaps"]
    assert "keycloak pull grant is not verified" in report["release_gaps"]


def test_registry_contract_rejects_shared_component_repository(tmp_path: Path) -> None:
    policy = yaml.safe_load(POLICY.read_text())
    broken = deepcopy(policy)
    broken["repositories"]["keycloak"]["repository"] = broken["repositories"][
        "backend"
    ]["repository"]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(broken, sort_keys=False))

    report = build_registry_policy_report(path)

    assert report["contract_status"] == "RED"
    assert report["release_eligible"] is False
    assert any("dedicated repository" in item for item in report["contract_violations"])


def test_registry_contract_requires_safe_retention_and_scoped_credentials(
    tmp_path: Path,
) -> None:
    policy = yaml.safe_load(POLICY.read_text())
    broken = deepcopy(policy)
    broken["retention"]["minimum_rollback_releases"] = 0
    broken["retention"]["delete_while_referenced"] = True
    broken["credentials"]["execution_cluster_pull"]["permissions"] = ["pull", "push"]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(broken, sort_keys=False))

    report = build_registry_policy_report(path)

    assert report["contract_status"] == "RED"
    joined = " ".join(report["contract_violations"])
    assert "rollback releases" in joined
    assert "referenced artifacts" in joined
    assert "pull-only" in joined


def test_ci_and_local_gate_validate_registry_contract() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    makefile = (ROOT / "Makefile").read_text()

    assert "python scripts/validate_artifact_registry.py" in workflow
    assert "artifact-registry-policy.json" in workflow
    assert "artifact-registry:" in makefile
    assert "python3 scripts/validate_artifact_registry.py" in makefile


def test_release_gate_remains_red_until_live_qualifications_exist() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validate_artifact_registry.py"),
            "--policy",
            str(POLICY),
            "--require-release-ready",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert '"contract_status": "GREEN-local"' in result.stdout
    assert '"release_eligible": false' in result.stdout


def _destination_receipt() -> dict:
    return {
        "schema_version": "launchpad.redhat.com/artifact-destination-qualification/v1",
        "cluster_id": "arena",
        "observed_at": "2026-09-20T06:00:00Z",
        "image": "quay.io/redhat-gpte/launchpad-backend@sha256:" + "a" * 64,
        "architecture": "amd64",
        "checks": {
            name: {"status": "passed", "evidence": [f"evidence/{name}.json"]}
            for name in (
                "credential",
                "certificate",
                "architecture",
                "signature",
                "exact_digest",
                "cold_pull",
                "cache_loss",
            )
        },
    }


def _write_receipt(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "receipt.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def test_destination_receipt_requires_every_recorded_check(tmp_path: Path) -> None:
    receipt = _destination_receipt()
    path = _write_receipt(tmp_path, receipt)

    report = evaluate_destination_qualification(POLICY, path)

    assert report["status"] == "GREEN-integration"
    assert report["eligible"] is True
    assert report["failures"] == []


def test_destination_receipt_fails_closed_on_missing_or_failed_proof(
    tmp_path: Path,
) -> None:
    receipt = _destination_receipt()
    del receipt["checks"]["cold_pull"]
    receipt["checks"]["signature"] = {"status": "failed", "evidence": []}
    path = _write_receipt(tmp_path, receipt)

    report = evaluate_destination_qualification(POLICY, path)

    assert report["status"] == "RED"
    assert report["eligible"] is False
    assert "required destination check is missing: cold_pull" in report["failures"]
    assert "destination check did not pass: signature" in report["failures"]
    assert "destination check has no evidence: signature" in report["failures"]


def test_destination_receipt_rejects_mutable_wrong_origin_or_architecture(
    tmp_path: Path,
) -> None:
    receipt = _destination_receipt()
    receipt["image"] = "registry.invalid/platform/backend:latest"
    receipt["architecture"] = "arm64"
    path = _write_receipt(tmp_path, receipt)

    report = evaluate_destination_qualification(POLICY, path)

    assert report["eligible"] is False
    assert "receipt image must use an immutable sha256 digest" in report["failures"]
    assert any("architecture arm64" in item for item in report["failures"])


def test_destination_receipt_rejects_inline_credentials(tmp_path: Path) -> None:
    receipt = _destination_receipt()
    receipt["checks"]["credential"]["token"] = "must-not-be-recorded"
    path = _write_receipt(tmp_path, receipt)

    report = evaluate_destination_qualification(POLICY, path)

    assert report["eligible"] is False
    assert any("inline credential field" in item for item in report["failures"])
