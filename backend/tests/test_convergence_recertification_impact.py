from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
IMPACT = ROOT / "evidence/convergence/recertification-impact-20261006.yaml"


def test_convergence_requires_a_platform_canary_without_overclaiming_lab_recertification() -> None:
    report = yaml.safe_load(IMPACT.read_text(encoding="utf-8"))
    decision = report["decision"]

    assert report["schema_version"] == (
        "launchpad.redhat.com/recertification-impact/v1"
    )
    assert decision["full_catalog_recertification_required"] is False
    assert decision["affected_lab_recertifications"] == []
    assert decision["platform_canary_required"] is True
    assert report["completed_proof"]["backend_non_local"]["passed"] == 2552
    assert report["completed_proof"]["requester_frontend"]["tests_passed"] == 81


def test_impact_report_keeps_automated_evidence_reuse_as_an_open_production_gate() -> None:
    report = yaml.safe_load(IMPACT.read_text(encoding="utf-8"))
    limitations = "\n".join(report["limitations"])
    remaining = "\n".join(report["remaining_gate"])

    assert "LP-S037" in limitations
    assert "Not every historical receipt binds" in limitations
    assert "zero residue" in remaining
    assert "targeted lab recertification" in remaining
