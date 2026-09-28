from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts/agentic-scale-certification-v1.yaml"
CERTIFICATION_PATH = ROOT / "certification/catalog/scale-agentic-blueprint.yaml"
CATALOG_PATH = ROOT / "catalog/scale-agentic-blueprint/catalog-item.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_scale_contract_extends_the_canonical_blueprint_and_401():
    contract = _load(CONTRACT_PATH)
    catalog = _load(CATALOG_PATH)

    assert contract["blueprint_id"] == catalog["metadata"]["shared_blueprint"]
    assert contract["catalog_item_id"] == catalog["catalog_item_id"]
    assert contract["prerequisites"]["catalog_item"] == "operate-agentic-blueprint"
    assert contract["prerequisites"]["required_state"] == "certified"


def test_scale_profiles_are_ordered_and_cannot_skip_promotion_stages():
    contract = _load(CONTRACT_PATH)
    profiles = contract["load_profiles"]

    assert [profile["seats"] for profile in profiles] == [1, 5, 25]
    assert all(profile["required_consecutive_green_runs"] == 3 for profile in profiles)
    assert contract["promotion"]["sequence"] == [1, 5, 25]
    assert contract["promotion"]["no_skipped_stages"] is True


def test_scale_contract_requires_quality_policy_and_honest_live_evidence():
    contract = _load(CONTRACT_PATH)

    assert contract["truth_boundary"]["certification_accepts_source_state"] == "live"
    assert contract["truth_boundary"]["projected_results_are_not_live_results"] is True
    assert contract["quality_gate"]["unsupported_claim_rate_percent"] == 0
    assert contract["service_objectives"]["policy"]["prohibited_action_execution_count"] == 0
    assert contract["service_objectives"]["evidence"]["maximum_incomplete_evidence_decisions"] == 0


def test_intel_xeon_proof_is_part_of_the_end_to_end_journey():
    contract = _load(CONTRACT_PATH)
    intel = contract["intel_xeon_evidence"]

    assert {"cpu_model", "cpu_allocation_cores", "inference_p95_ms", "throughput_tokens_per_second"} <= set(intel["required_dimensions"])
    assert intel["attribution"]["journey_id_required"] is True
    assert intel["attribution"]["approved_telemetry_source_required"] is True


def test_resilience_proves_safe_state_and_recovery():
    contract = _load(CONTRACT_PATH)
    scenarios = contract["resilience_scenarios"]

    assert {scenario["id"] for scenario in scenarios} == {
        "agent-pod-loss",
        "mcp-unavailable",
        "inference-timeout",
        "policy-denial",
        "overload-backpressure",
        "evidence-incomplete",
    }
    assert all(scenario["expected_safe_state"] for scenario in scenarios)
    assert all(scenario["maximum_recovery_seconds"] >= 0 for scenario in scenarios)


def test_certification_is_non_executable_until_blockers_are_cleared():
    certification = _load(CERTIFICATION_PATH)
    catalog = _load(CATALOG_PATH)

    assert certification["metadata"]["catalog_item_id"] == catalog["catalog_item_id"]
    assert certification["spec"]["state"] == "charter"
    assert certification["spec"]["execution_enabled"] is False
    assert certification["spec"]["execution_blockers"]
    assert certification["spec"]["rubric"]["required_score"] == 100
    assert sum(category["weight"] for category in certification["spec"]["rubric"]["categories"]) == 100

