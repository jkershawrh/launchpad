from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_CONTRACT_PATH = ROOT / "contracts/agentic-workload-scale-v1.yaml"
DELIVERY_CONTRACT_PATH = ROOT / "contracts/catalog-scale-delivery-certification-v1.yaml"
CERTIFICATION_PATH = ROOT / "certification/catalog/scale-agentic-blueprint.yaml"
WORKLOAD_CHARTER_PATH = ROOT / "certification/workload/scale-agentic-blueprint.yaml"
CATALOG_PATH = ROOT / "catalog/scale-agentic-blueprint/catalog-item.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_scale_contract_extends_the_canonical_blueprint_and_401():
    contract = _load(WORKLOAD_CONTRACT_PATH)
    catalog = _load(CATALOG_PATH)

    assert contract["blueprint_id"] == catalog["metadata"]["shared_blueprint"]
    assert contract["catalog_item_id"] == catalog["catalog_item_id"]
    assert contract["prerequisites"]["catalog_item"] == "operate-agentic-blueprint"
    assert contract["prerequisites"]["required_state"] == "certified"


def test_workload_profiles_scale_one_environment_without_participant_seats():
    contract = _load(WORKLOAD_CONTRACT_PATH)
    profiles = contract["workload_profiles"]

    assert [profile["id"] for profile in profiles] == ["baseline", "sustained", "pressure"]
    assert [profile["agent_replicas"] for profile in profiles] == [1, 2, 3]
    assert [profile["concurrent_journeys"] for profile in profiles] == [1, 5, 10]
    assert all("seats" not in profile for profile in profiles)


def test_launchpad_delivery_contract_owns_seat_promotion_and_cleanup():
    contract = _load(DELIVERY_CONTRACT_PATH)

    assert [profile["seats"] for profile in contract["seat_profiles"]] == [1, 5, 25]
    assert contract["promotion"]["sequence"] == [1, 5, 25]
    assert contract["delivery_objectives"]["zero_residue_required"] is True


def test_scale_contract_requires_quality_policy_and_honest_live_evidence():
    contract = _load(WORKLOAD_CONTRACT_PATH)

    assert contract["truth_boundary"]["lab_completion_accepts_source_state"] == "live"
    assert contract["truth_boundary"]["projected_results_are_not_live_results"] is True
    assert contract["quality_gate"]["unsupported_claim_rate_percent"] == 0
    assert contract["service_objectives"]["policy"]["prohibited_action_execution_count"] == 0
    assert contract["service_objectives"]["evidence"]["maximum_incomplete_evidence_decisions"] == 0


def test_intel_xeon_proof_is_part_of_the_end_to_end_journey():
    contract = _load(WORKLOAD_CONTRACT_PATH)
    intel = contract["intel_xeon_evidence"]

    assert {"inference_p95_ms", "input_tokens", "output_tokens"} <= set(intel["request_attributed"])
    assert {"cpu_model", "cpu_allocation_cores", "throughput_tokens_per_second"} <= set(intel["shared_endpoint"])
    assert intel["shared_metrics_must_not_be_presented_as_per_journey"] is True


def test_agent_sandbox_governs_execution_and_keeps_kata_optional():
    contract = _load(WORKLOAD_CONTRACT_PATH)
    sandbox = contract["agent_sandbox"]

    assert {
        "dedicated_service_account",
        "least_privilege_rbac",
        "allowlisted_mcp_tools",
        "namespace_network_boundary",
        "no_direct_model_action_authority",
        "allowed_and_denied_request_audit",
    } <= set(sandbox["required_controls"])
    assert sandbox["optional_stronger_isolation"]["technology"] == (
        "openshift_sandboxed_containers"
    )
    assert sandbox["optional_stronger_isolation"]["runtime_class"] == "kata"
    assert sandbox["optional_stronger_isolation"][
        "unavailable_must_not_be_presented_as_active"
    ] is True


def test_resilience_proves_safe_state_and_recovery():
    contract = _load(WORKLOAD_CONTRACT_PATH)
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


def test_certification_executes_only_as_rehearsal_destination_qualification():
    certification = _load(CERTIFICATION_PATH)
    catalog = _load(CATALOG_PATH)

    assert certification["metadata"]["catalog_item_id"] == catalog["catalog_item_id"]
    assert certification["spec"]["state"] == "destination-qualification"
    assert certification["spec"]["execution_enabled"] is True
    assert certification["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "evidence_source", "equals": "rehearsal"} in certification["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "live_claim", "equals": False} in certification["spec"]["seat_probe"]["json_assertions"]
    assert certification["spec"]["execution_blockers"]
    assert certification["spec"]["rubric"]["required_score"] == 100
    assert sum(category["weight"] for category in certification["spec"]["rubric"]["categories"]) == 100
    assert {category["id"] for category in certification["spec"]["rubric"]["categories"]} == {
        "contract_and_provenance",
        "provisioning_and_capacity",
        "participant_probe",
        "isolation_and_access",
        "delivery_observability",
        "lifecycle",
    }


def test_workload_execution_has_a_separate_fail_closed_charter():
    charter = _load(WORKLOAD_CHARTER_PATH)

    assert charter["kind"] == "WorkloadScaleCharter"
    assert charter["spec"]["execution_enabled"] is False
    assert charter["spec"]["profiles"] == ["baseline", "sustained", "pressure"]
    assert charter["spec"]["governing_contract"] == "contracts/agentic-workload-scale-v1.yaml"
