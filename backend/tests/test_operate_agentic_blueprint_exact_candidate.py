from pathlib import Path

import yaml

from app.services.catalog_certification import build_certification_plan


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/operate-agentic-blueprint/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/operate-agentic-blueprint.yaml"
CERTIFICATION = ROOT / "certification/catalog/operate-agentic-blueprint.yaml"
REVIEW = ROOT / "evidence/lab-experience-review-20260930.yaml"


def test_401_exact_candidate_pins_are_consistent_across_catalog_and_intake():
    catalog = yaml.safe_load(CATALOG.read_text())
    intake = yaml.safe_load(INTAKE.read_text())
    metadata = catalog["metadata"]

    assert catalog["version"] == intake["catalog"]["version"] == "0.1.1"
    assert metadata["showroom_content_ref"] == intake["sources"]["showroom"]["revision"]
    assert metadata["source_content_revision"] == metadata["showroom_content_ref"]
    assert metadata["workload_revision"] == intake["sources"]["workload"]["revision"]
    assert metadata["certification_transfer"] == intake["learning"]["certification_transfer"] == "none"
    assert metadata["max_workshop_seats"] == intake["certification"]["max_workshop_seats"] == 1
    assert metadata["certification_stage"] == intake["certification"]["stage"] == "1-seat-certified"
    assert intake["certification"]["certified_seats"] == 1
    assert metadata["public_access_certification_stage"] == "one-seat-certified"
    assert intake["certification"]["public_access_stage"] == "one-seat-certified"
    assert metadata["public_max_workshop_seats"] == 1
    assert intake["certification"]["public_max_workshop_seats"] == 1
    assert intake["runtime"]["allowed_exposure_policies"] == [
        "internal",
        "public_code",
    ]
    assert metadata["source_references"]["certification_evidence"] == (
        "evidence/runs/flightpath-live-20261002-agentic-ai-401-public-1seat-r4.json"
    )
    assert metadata["activation_blockers"] == intake["certification"]["activation_blockers"]
    assert metadata["activation_blockers"] == [
        "Prove independent guardrail and inference outage tests, fail-closed behavior, and recovery without relying on co-located-process restarts.",
        "Add certified OpenTelemetry collection and a learner-visible correlated trace without exposing secrets or hidden model reasoning.",
        "Validate namespace-scoped GitOps drift detection and pipeline-based evaluation before presenting those operator capabilities as live.",
        "Measure and publish Intel Xeon endpoint latency, token usage, and CPU allocation through an approved telemetry source.",
    ]


def test_401_one_seat_contract_proves_live_model_route_and_restoration():
    contract = yaml.safe_load(CERTIFICATION.read_text())
    assert contract["spec"]["allowed_exposure_policies"] == [
        "internal",
        "public_code",
    ]
    assertions = contract["spec"]["seat_probe"]["json_assertions"]

    for assertion in (
        {"path": "semantic_routing.classification_status", "equals": "ok"},
        {"path": "semantic_routing.classifier", "equals": "llm-fallback"},
        {"path": "semantic_routing.selected_model", "equals": "simple"},
        {"path": "semantic_routing.selected_workflow", "equals": "standard"},
        {"path": "intel_xeon_inference.semantic_route_completed", "equals": True},
        {"path": "learner_policy.rollback_restored_baseline", "equals": True},
        {"path": "learner_policy.configmap_removed", "equals": True},
    ):
        assert assertion in assertions


def test_401_public_proof_uses_admin_override_while_candidate_is_draft():
    contract = yaml.safe_load(CERTIFICATION.read_text())
    intake = yaml.safe_load(INTAKE.read_text())

    plan = build_certification_plan(
        contract,
        intake=intake,
        seats=1,
        exposure_policy="public_code",
    )

    assert plan["current_certified_seats"] == 1
    assert plan["certification_override"] is True
    assert plan["execution_eligible"] is True


def test_401_review_records_exact_source_and_artifact_boundary():
    review = yaml.safe_load(REVIEW.read_text())["labs"]["operate-agentic-blueprint"]
    source_state = review["source_state"]

    assert source_state["published_revision"] == "d12a47688d57b9d72fe8c069bad45cb0baad94aa"
    assert source_state["catalog_pinned_revision"] == source_state["published_revision"]
    assert source_state["workload_revision"] == "d7c7e686d6513a77de685569b27863c9269c990f"
    assert source_state["runtime_source_revision"] == "43889bc9444f9ef07f5b1a88e7de534af9647264"
    assert source_state["immutable_images"] == {
        "runtime": "ghcr.io/jkershawrh/multi-agent-quickstart@sha256:087d9548c044f1af641530f1913609715675e2eadf6dfe8c68c05bcad0cc7c86",
        "presentation": "quay.io/rh-ee-jkershaw/launchpad-operate-agentic-blueprint-presentation@sha256:2aee08aaac09e296725954a9450ffc87240b9a9ef458a291916127871259c580",
    }
    assert source_state["certification_transfer"] == "none"
    assert review["overall_status"] == "one-seat-live-certified-draft"
    assert review["live_certification"]["result"] == "GREEN-live"
    assert review["live_certification"]["rubric_score"] == 100
