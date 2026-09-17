import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vef_export_pilot.py"
SPEC = importlib.util.spec_from_file_location("vef_export_pilot", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def pilot_input() -> dict:
    return {
        "schema_version": "launchpad.vef-pilot-input.v1alpha1",
        "pilot_id": "75-user-90-seat",
        "period": {"start": "2026-09-17T13:00:00Z", "end": "2026-09-17T21:00:00Z"},
        "population": {
            "provisioned_seats": 90,
            "enrolled_users": 75,
            "active_users": 70,
            "successful_journeys": 68,
            "unknown_outcomes": 0,
        },
        "baseline": {
            "method": "matched_control",
            "independent": True,
            "matched_population": True,
            "successful_journeys": 68,
            "operating_cost_usd": 1000,
        },
        "treatment": {
            "method": "matched_control",
            "independent": True,
            "matched_population": True,
            "successful_journeys": 68,
            "operating_cost_usd": 800,
        },
        "safety": {
            "accounting_complete": True,
            "failed_journeys": 2,
            "probe_failures": 0,
            "restart_increase": 0,
            "cleanup_residue": 0,
            "failure_threshold_breached": False,
        },
        "ai_usage": {
            "measurement_state": "authoritative",
            "actual_requests": 1000,
            "input_tokens": 100000,
            "output_tokens": 50000,
            "inference_cost_usd": 75,
        },
        "economics": {
            "currency": "USD",
            "engineering_effort": [
                {"activity": "pilot_design", "lifecycle": "initial", "role": "engineer", "hours": 2, "loaded_rate_usd": 100, "source": "bounded_work_log"},
                {"activity": "pilot_support", "lifecycle": "recurring", "role": "engineer", "hours": 1, "loaded_rate_usd": 100, "source": "bounded_work_log"},
            ],
            "support_hours": 2,
            "support_loaded_rate_usd": 50,
            "other_realization_cost_usd": 25,
            "marginal_delivery_cost_measured": True,
        },
        "attribution": {"product_share": 0.6, "competing_factors": ["facilitator experience", "platform contention"]},
        "approvals": {
            "manual_acceptance_complete": True,
            "security_triage_complete": True,
            "customer_validated": True,
            "finance_approved": True,
            "privacy_approved": True,
        },
        "evidence_sources": ["sanitized/pilot-summary.json", "evidence/runs/release-decision.json"],
    }


def test_complete_pilot_is_value_eligible_and_keeps_population_distinct():
    report = MODULE.build_export(pilot_input())
    assert report["value_eligible"] is True
    assert report["proof_state"] == "decision-grade"
    measurement = report["claim"]["measurement"]
    assert measurement["provisioned_seats"] == 90
    assert measurement["enrolled_users"] == 75
    assert measurement["active_users"] == 70
    assert report["claim"]["financial_model"]["gross_value"] == 200.0
    assert report["claim"]["realization_cost"] == 425.0


def test_current_direct_endpoint_boundary_fails_closed():
    data = pilot_input()
    data["ai_usage"] = {
        "measurement_state": "unavailable",
        "actual_requests": None,
        "input_tokens": None,
        "output_tokens": None,
        "inference_cost_usd": None,
    }
    report = MODULE.build_export(data)
    assert report["value_eligible"] is False
    assert report["proof_state"] == "directional"
    assert report["claim"]["financial_model"]["gross_value"] == 0.0
    assert report["claim"]["measurement"]["observed_gross_value_candidate_usd"] == 200.0
    assert any("not authoritative" in gap for gap in report["eligibility_gaps"])


def test_unknown_outcomes_and_cleanup_residue_are_not_zero():
    data = pilot_input()
    data["population"]["unknown_outcomes"] = 1
    data["safety"]["cleanup_residue"] = 1
    report = MODULE.build_export(data)
    assert report["value_eligible"] is False
    assert "participant outcomes contain unknown states" in report["eligibility_gaps"]
    assert "lab cleanup has residue" in report["eligibility_gaps"]


def test_enrolled_users_cannot_exceed_provisioned_seats():
    data = pilot_input()
    data["population"]["enrolled_users"] = 91
    try:
        MODULE.build_export(data)
        assert False, "expected validation failure"
    except ValueError as exc:
        assert "cannot exceed provisioned" in str(exc)


def test_sensitive_or_raw_fields_are_rejected():
    for field in (
        "prompt",
        "response",
        "email",
        "participant_id",
        "namespace",
        "cluster",
        "credentials",
        "secret",
    ):
        data = pilot_input()
        data["unexpected"] = {field: "not-exportable"}
        try:
            MODULE.build_export(data)
            assert False, f"expected {field} rejection"
        except ValueError as exc:
            assert "sensitive or raw field" in str(exc)


def test_versioned_value_evidence_export_is_deterministic():
    data = pilot_input()
    MODULE.validate(data)
    report = MODULE.build_export(data)
    value_evidence = report["claim"]["measurement"]["value_evidence_contract"]
    assert value_evidence == "vef.claim.v1alpha1"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "input.json"
        first = Path(tmp) / "first.json"
        second = Path(tmp) / "second.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        for output in (first, second):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
        assert first.read_bytes() == second.read_bytes()
