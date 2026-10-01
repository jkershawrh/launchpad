from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_CONTRACT_PATH = ROOT / "contracts/agentic-workload-scale-v1.yaml"
DELIVERY_CONTRACT_PATH = ROOT / "contracts/catalog-scale-delivery-certification-v1.yaml"
CERTIFICATION_PATH = ROOT / "certification/catalog/scale-agentic-blueprint.yaml"
WORKLOAD_CHARTER_PATH = ROOT / "certification/workload/scale-agentic-blueprint.yaml"
CATALOG_PATH = ROOT / "catalog/scale-agentic-blueprint/catalog-item.yaml"
INTAKE_PATH = ROOT / "catalog-onboarding/scale-agentic-blueprint.yaml"
CERTIFIER_PATH = ROOT / "scripts/certify-scale-agentic-blueprint-seat.sh"
REVIEW_PATH = ROOT / "evidence/lab-experience-review-20260930.yaml"
SOURCE_REVISION = "173f019da79d0d55431457ff24ed3e7253d98b23"
PRESENTATION_IMAGE = "ghcr.io/jkershawrh/agentic-scale-501-presentation@sha256:c69aa83eafde91e67544d79f804ab3849a0402522277cbb21a72bc649866a1cb"
QUALIFIER_IMAGE = "ghcr.io/jkershawrh/agentic-scale-501-qualifier@sha256:e33dd9066e36d01e0b90143d7752004c15128b21f42b5f4c1aac465b9a5be7a0"


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
    assert [page["id"] for page in certification["spec"]["showroom"]["pages"]] == [
        "welcome",
        "baseline",
        "controlled-pressure",
        "score-review",
        "close-handoff",
    ]
    assert all(
        page["path"].startswith("/www/agentic-scale-501/")
        for page in certification["spec"]["showroom"]["pages"]
    )
    assert sum(category["weight"] for category in certification["spec"]["rubric"]["categories"]) == 100
    assert {category["id"] for category in certification["spec"]["rubric"]["categories"]} == {
        "contract_and_provenance",
        "provisioning_and_capacity",
        "participant_rehearsal",
        "isolation_and_access",
        "lifecycle",
    }


def test_one_seat_rehearsal_rubric_uses_only_runner_emitted_gates():
    certification = _load(CERTIFICATION_PATH)
    emitted_gates = {
        "contract_valid",
        "evidence_hashed",
        "capacity_passed",
        "single_cluster_assignment",
        "all_seats_ready",
        "ready_within_limit",
        "showroom_pages_passed",
        "seat_probes_passed",
        "namespace_isolation_passed",
        "sensitive_values_absent",
        "cleanup_completed",
        "zero_residue_cleanup",
        "model_keys_revoked",
    }
    required = {
        gate
        for category in certification["spec"]["rubric"]["categories"]
        for gate in category["requires"]
    }

    assert required <= emitted_gates


def test_one_seat_experience_proof_does_not_claim_multi_seat_or_live_inference():
    certification = _load(CERTIFICATION_PATH)
    catalog = _load(CATALOG_PATH)
    intake = _load(INTAKE_PATH)

    assert intake["certification"]["certified_seats"] == 0
    assert intake["certification"]["max_workshop_seats"] == 1
    assert catalog["metadata"]["max_workshop_seats"] == 1
    assert catalog["metadata"]["required_models"] == []
    assert catalog["metadata"]["inference_endpoint"] == "none"
    assert catalog["metadata"]["workload_gitops_ready"] is True
    assert catalog["metadata"]["workload_routes"] == {
        "presentation": "agentic-scale-501-presentation",
        "qualifier": "agentic-scale-501-qualifier",
    }
    assert catalog["metadata"]["promotion_sequence"] == [1]
    assert intake["certification"]["promotion_sequence"] == [1]
    assert intake["certification"]["stage"] == "immutable-source-published"
    assert [profile["seats"] for profile in certification["spec"]["scale_profiles"]] == [1]
    assert certification["spec"]["seat_probe"]["json_assertions"][:4] == [
        {"path": "result", "equals": "GREEN-destination-rehearsal-seat"},
        {"path": "cluster_ref", "equals": "flightpath"},
        {"path": "evidence_source", "equals": "rehearsal"},
        {"path": "live_claim", "equals": False},
    ]
    blockers = " ".join(intake["certification"]["activation_blockers"])
    assert "five- and twenty-five-seat scale certification is deferred" in blockers


def test_rehearsal_certifier_proves_exact_artifacts_without_model_participation():
    certification = _load(CERTIFICATION_PATH)
    assertions = certification["spec"]["seat_probe"]["json_assertions"]

    for assertion in (
        {"path": "provenance.source_revision", "equals": SOURCE_REVISION},
        {"path": "runtime_images.presentation", "equals": PRESENTATION_IMAGE},
        {"path": "runtime_images.qualifier", "equals": QUALIFIER_IMAGE},
        {"path": "inference.synthetic", "equals": True},
        {"path": "inference.model_participated", "equals": False},
    ):
        assert assertion in assertions

    certifier = CERTIFIER_PATH.read_text()
    assert SOURCE_REVISION in certifier
    assert PRESENTATION_IMAGE in certifier
    assert QUALIFIER_IMAGE in certifier
    assert '.inference.model == "deterministic-rehearsal-model"' in certifier
    assert '.inference.endpoint == "local://agentic-scale-501/rehearsal"' in certifier
    assert "grep -q 'SCALE PROOF'" in certifier
    assert "! grep -q 'LIVE WORKLOAD'" in certifier
    assert "curl_options=(-fsS" in certifier
    assert "curl_options=(-fsSk" not in certifier
    assert "whoami --show-console" in certifier


def test_review_evidence_marks_the_exact_release_as_published_and_nontransferable():
    review = _load(REVIEW_PATH)["labs"]["scale-agentic-blueprint"]

    assert review["overall_status"] in {"immutable-source-published-draft", "one-seat-live-certified-draft"}
    assert review["source_state"]["published_revision"] == SOURCE_REVISION
    assert review["source_state"]["certification_transfer"] == "none"


def test_workload_execution_has_a_separate_fail_closed_charter():
    charter = _load(WORKLOAD_CHARTER_PATH)

    assert charter["kind"] == "WorkloadScaleCharter"
    assert charter["spec"]["execution_enabled"] is False
    assert charter["spec"]["profiles"] == ["baseline", "sustained", "pressure"]
    assert charter["spec"]["governing_contract"] == "contracts/agentic-workload-scale-v1.yaml"
