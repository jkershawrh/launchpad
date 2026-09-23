from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_permanent_home_intake.py"


def module():
    spec = importlib.util.spec_from_file_location("home_intake", SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(loaded)
    return loaded


def valid_intake(tmp_path):
    categories = module().REQUIRED_CATEGORIES
    evidence_dir = tmp_path / "evidence" / "intake"
    evidence_dir.mkdir(parents=True)
    for category in categories:
        (evidence_dir / f"{category}.json").write_text("{}")
    return {
        "schema": "launchpad.redhat.com/permanent-home-intake/v1",
        "target_id": "candidate-home",
        "release_digest": "sha256:" + "a" * 64,
        "checks": {
            category: {
                "status": "pass",
                "evidence": [f"evidence/intake/{category}.json"],
                "owner": "platform-team",
            }
            for category in categories
        },
        "decision": {"approved_by": "reviewer-1", "accepted_gaps": []},
    }


def test_complete_intake_is_ready_for_bootstrap_only(tmp_path):
    result = module().evaluate(valid_intake(tmp_path), tmp_path)
    assert result["ready_for_bootstrap"] is True
    assert result["authorizes_cutover"] is False
    assert result["failed_checks"] == []


def test_missing_category_or_evidence_fails_closed(tmp_path):
    intake = valid_intake(tmp_path)
    del intake["checks"]["backup_restore"]
    intake["checks"]["registry"]["evidence"] = []
    result = module().evaluate(intake, tmp_path)
    assert result["ready_for_bootstrap"] is False
    assert "backup_restore" in result["failed_checks"]
    assert "registry" in result["failed_checks"]


def test_accepted_gap_never_turns_failed_critical_check_green(tmp_path):
    intake = valid_intake(tmp_path)
    intake["checks"]["identity"]["status"] = "fail"
    intake["decision"]["accepted_gaps"] = ["identity"]
    assert module().evaluate(intake, tmp_path)["ready_for_bootstrap"] is False


def test_rejects_url_or_secret_value_in_evidence_ref(tmp_path):
    intake = valid_intake(tmp_path)
    intake["checks"]["secrets"]["evidence"] = ["https://example.test/key?token=secret"]
    result = module().evaluate(intake, tmp_path)
    assert result["ready_for_bootstrap"] is False
    assert "secrets" in result["failed_checks"]
    assert "token=secret" not in json.dumps(result).lower()


def test_missing_signoff_or_mutable_release_fails_closed(tmp_path):
    intake = valid_intake(tmp_path)
    intake["decision"]["approved_by"] = ""
    intake["release_digest"] = "latest"
    result = module().evaluate(intake, tmp_path)
    assert result["ready_for_bootstrap"] is False
    assert "signoff" in result["failed_checks"]
    assert "immutable_release" in result["failed_checks"]


def test_missing_evidence_file_or_traversal_fails_closed(tmp_path):
    intake = valid_intake(tmp_path)
    (tmp_path / "evidence/intake/storage.json").unlink()
    intake["checks"]["identity"]["evidence"] = ["../elsewhere.json"]
    result = module().evaluate(intake, tmp_path)
    assert result["ready_for_bootstrap"] is False
    assert "storage" in result["failed_checks"]
    assert "identity" in result["failed_checks"]


def test_unknown_fields_and_missing_gap_decision_fail_closed(tmp_path):
    intake = valid_intake(tmp_path)
    intake["database_password"] = "do-not-report-this"
    del intake["decision"]["accepted_gaps"]
    result = module().evaluate(intake, tmp_path)
    assert result["ready_for_bootstrap"] is False
    assert "unexpected_fields" in result["failed_checks"]
    assert "accepted_gaps" in result["failed_checks"]
    assert "do-not-report-this" not in json.dumps(result)
