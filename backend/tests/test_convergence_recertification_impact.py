from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
IMPACT = ROOT / "evidence/convergence/recertification-impact-20261006.yaml"
CANARY = ROOT / "evidence/convergence/platform-canary-20261006.yaml"


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


def test_live_platform_canary_closes_the_selective_recertification_gate() -> None:
    proof = yaml.safe_load(CANARY.read_text(encoding="utf-8"))

    assert proof["schema_version"] == "launchpad.redhat.com/platform-canary/v1"
    assert proof["source"]["deployment_commit"] == "4e25830f"
    assert proof["scope"]["cluster"] == "flightpath"
    assert proof["preconditions"]["ready_nodes"] == 6
    assert proof["rollout"]["requester"]["result"] == "pass"
    assert proof["rollout"]["admin"]["result"] == "pass"
    assert proof["canary"]["validation"]["checks_passed"] == 6
    assert proof["canary"]["validation"]["repeatability_score"] == 100
    assert proof["cleanup"]["namespace_count"] == 0
    assert proof["cleanup"]["route_count"] == 0
    assert proof["cleanup"]["rolebinding_count"] == 0
    assert proof["cleanup"]["argocd_application_count"] == 0
    assert proof["cleanup"]["active_session_count"] == 0
    assert proof["decision"]["platform_canary"] == "GREEN-live"
    assert proof["decision"]["blanket_lab_recertification_required"] is False
    assert proof["decision"]["targeted_lab_recertification_required"] == []
