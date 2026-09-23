import copy
import hashlib
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
        "schema_version": "launchpad.vef-pilot-input.v1alpha2",
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
        "analytics": {
            "track_outcomes": [
                {
                    "track_id": "serve-llms",
                    "provisioned_seats": 30,
                    "activated_journeys": 24,
                    "successful_journeys": 23,
                    "failed_journeys": 1,
                    "unknown_outcomes": 0,
                    "evidence_state": "authoritative",
                },
                {
                    "track_id": "build-agent",
                    "provisioned_seats": 30,
                    "activated_journeys": 24,
                    "successful_journeys": 23,
                    "failed_journeys": 1,
                    "unknown_outcomes": 0,
                    "evidence_state": "authoritative",
                },
                {
                    "track_id": "agent-framework",
                    "provisioned_seats": 30,
                    "activated_journeys": 22,
                    "successful_journeys": 22,
                    "failed_journeys": 0,
                    "unknown_outcomes": 0,
                    "evidence_state": "authoritative",
                },
            ],
            "platform_lifecycle": {
                "measurement_state": "authoritative",
                "orders_requested": 3,
                "seats_requested": 90,
                "seats_ready": 90,
                "seats_reclaimed": 90,
                "provisioning_p95_seconds": 960,
                "reclaim_p95_seconds": 100,
                "human_interventions": 2,
                "residue_count": 0,
            },
            "cost_allocation": {
                "measurement_state": "authoritative",
                "allocation_basis": "successful_journey",
                "shared_platform_cost_usd": 300,
                "delivery_cost_usd": 425,
                "allocated_inference_cost_usd": 75,
                "unallocated_cost_usd": 0,
                "cost_center_ready": True,
                "chargeback_ready": True,
            },
        },
        "economics": {
            "currency": "USD",
            "engineering_effort": [
                {
                    "activity": "pilot_design",
                    "lifecycle": "initial",
                    "role": "engineer",
                    "hours": 2,
                    "loaded_rate_usd": 100,
                    "source": "bounded_work_log",
                },
                {
                    "activity": "pilot_support",
                    "lifecycle": "recurring",
                    "role": "engineer",
                    "hours": 1,
                    "loaded_rate_usd": 100,
                    "source": "bounded_work_log",
                },
            ],
            "support_hours": 2,
            "support_loaded_rate_usd": 50,
            "other_realization_cost_usd": 25,
            "marginal_delivery_cost_measured": True,
        },
        "attribution": {
            "product_share": 0.6,
            "competing_factors": ["facilitator experience", "platform contention"],
        },
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
    data["analytics"]["track_outcomes"][0]["unknown_outcomes"] = 1
    data["analytics"]["track_outcomes"][0]["activated_journeys"] += 1
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
    assert value_evidence == "vef.claim.v1alpha2"
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


def test_track_lifecycle_and_cost_analytics_are_exported_without_identity_data():
    report = MODULE.build_export(pilot_input())
    analytics = report["analytics"]
    assert analytics["analytics_ready"] is True
    assert analytics["chargeback_ready"] is True
    assert analytics["track_outcomes"][0]["track_id"] == "agent-framework"
    assert analytics["track_outcomes"][2]["track_id"] == "serve-llms"
    assert analytics["platform_lifecycle"]["seats_reclaimed"] == 90
    assert analytics["cost_allocation"]["total_allocated_cost_usd"] == 800.0
    assert analytics["cost_allocation"]["cost_per_successful_journey_usd"] == 11.76


def test_partial_track_evidence_is_visible_and_fails_closed():
    data = pilot_input()
    data["analytics"]["track_outcomes"][0]["evidence_state"] = "partial"
    report = MODULE.build_export(data)
    assert report["value_eligible"] is False
    assert report["analytics"]["analytics_ready"] is False
    assert report["analytics"]["chargeback_ready"] is False
    assert any(
        "track outcome evidence is not authoritative" in gap for gap in report["eligibility_gaps"]
    )


def test_unallocated_cost_is_not_silently_treated_as_chargeback_ready():
    data = pilot_input()
    data["analytics"]["cost_allocation"]["unallocated_cost_usd"] = 50
    report = MODULE.build_export(data)
    assert report["value_eligible"] is False
    assert report["analytics"]["chargeback_ready"] is False
    assert report["analytics"]["cost_allocation"]["unallocated_cost_usd"] == 50.0
    assert any("cost remains unallocated" in gap for gap in report["eligibility_gaps"])


def test_unavailable_cost_amounts_remain_unknown_instead_of_becoming_zero():
    data = pilot_input()
    allocation = data["analytics"]["cost_allocation"]
    allocation.update(
        measurement_state="unavailable",
        shared_platform_cost_usd=None,
        delivery_cost_usd=None,
        allocated_inference_cost_usd=None,
        unallocated_cost_usd=None,
        cost_center_ready=False,
        chargeback_ready=False,
    )
    report = MODULE.build_export(data)
    exported = report["analytics"]["cost_allocation"]
    assert report["value_eligible"] is False
    assert report["analytics"]["chargeback_ready"] is False
    assert exported["total_allocated_cost_usd"] is None
    assert exported["cost_per_successful_journey_usd"] is None
    assert any("amounts are unavailable" in gap for gap in report["eligibility_gaps"])


def test_track_totals_must_reconcile_to_population():
    data = pilot_input()
    data["analytics"]["track_outcomes"][0]["successful_journeys"] += 1
    data["analytics"]["track_outcomes"][0]["activated_journeys"] += 1
    try:
        MODULE.build_export(data)
        assert False, "expected reconciliation failure"
    except ValueError as exc:
        assert "track successful journeys must equal population.successful_journeys" in str(exc)


def test_zero_successful_journeys_does_not_divide_by_zero_or_claim_value():
    data = pilot_input()
    data["population"]["successful_journeys"] = 0
    data["population"]["active_users"] = 2
    data["safety"]["failed_journeys"] = 2
    for track in data["analytics"]["track_outcomes"]:
        track["successful_journeys"] = 0
        track["failed_journeys"] = 0
        track["activated_journeys"] = 0
    data["analytics"]["track_outcomes"][0]["failed_journeys"] = 1
    data["analytics"]["track_outcomes"][0]["activated_journeys"] = 1
    data["analytics"]["track_outcomes"][1]["failed_journeys"] = 1
    data["analytics"]["track_outcomes"][1]["activated_journeys"] = 1
    report = MODULE.build_export(data)
    assert report["value_eligible"] is False
    assert report["analytics"]["cost_allocation"]["cost_per_successful_journey_usd"] is None
    assert any("no successful journeys" in gap for gap in report["eligibility_gaps"])


def test_legacy_v1alpha1_input_preserves_legacy_output_contract():
    data = pilot_input()
    data["schema_version"] = "launchpad.vef-pilot-input.v1alpha1"
    data.pop("analytics")
    report = MODULE.build_export(data)
    assert report["schema_version"] == "launchpad.vef-pilot-claim.v1alpha1"
    assert set(report) == {
        "schema_version",
        "proof_state",
        "value_eligible",
        "eligibility_gaps",
        "claim",
        "notice",
    }
    assert "analytics" not in report
    assert report["claim"]["measurement"]["value_evidence_contract"] == "vef.claim.v1alpha1"
    assert report["value_eligible"] is True
    assert report["claim"]["financial_model"]["gross_value"] == 200.0
    assert report["claim"]["realization_cost"] == 425.0
    rendered = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    assert (
        hashlib.sha256(rendered).hexdigest()
        == "fd73ccfa441290cd37d0662b8a4661535bc0e070774e1899babc8fc7daff68b4"
    )


def test_v1alpha2_requires_analytics_but_v1alpha1_does_not():
    data = pilot_input()
    data.pop("analytics")
    try:
        MODULE.build_export(data)
        assert False, "expected v1alpha2 analytics requirement"
    except ValueError as exc:
        assert "analytics" in str(exc)
    data["schema_version"] = "launchpad.vef-pilot-input.v1alpha1"
    assert MODULE.build_export(data)["schema_version"] == "launchpad.vef-pilot-claim.v1alpha1"


def test_legacy_v1alpha1_still_rejects_invalid_economics_and_governance():
    legacy = pilot_input()
    legacy["schema_version"] = "launchpad.vef-pilot-input.v1alpha1"
    legacy.pop("analytics")

    invalid_cases = []
    invalid_economics = copy.deepcopy(legacy)
    invalid_economics["economics"]["currency"] = "EUR"
    invalid_cases.append((invalid_economics, "economics.currency"))

    invalid_attribution = copy.deepcopy(legacy)
    invalid_attribution["attribution"]["product_share"] = 2
    invalid_cases.append((invalid_attribution, "attribution.product_share"))

    invalid_approvals = copy.deepcopy(legacy)
    invalid_approvals["approvals"].pop("privacy_approved")
    invalid_cases.append((invalid_approvals, "approvals.privacy_approved"))

    invalid_evidence = copy.deepcopy(legacy)
    invalid_evidence["evidence_sources"] = []
    invalid_cases.append((invalid_evidence, "evidence_sources"))

    for data, expected_error in invalid_cases:
        try:
            MODULE.build_export(data)
            assert False, f"expected legacy rejection for {expected_error}"
        except ValueError as exc:
            assert expected_error in str(exc)
