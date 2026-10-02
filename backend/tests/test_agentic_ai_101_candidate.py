from pathlib import Path

from app.services.catalog_certification import (
    load_certification_contract,
    validate_certification_contract,
)
from app.services.catalog_onboarding import load_intake, validate_intake


ROOT = Path(__file__).resolve().parents[2]
INTAKE_PATH = ROOT / "catalog-onboarding/agentic-ai-101.yaml"
CONTRACT_PATH = ROOT / "certification/catalog/agentic-ai-101.yaml"
PROBE_PATH = ROOT / "scripts/certify-agentic-ai-101-seat.sh"

PRESENTATION_IMAGE = (
    "ghcr.io/jkershawrh/agentic-ai-101-presentation@"
    "sha256:311b0ee016af01c76f8339ccc14006060d4e9d1fb5feab856c0c15aefa426d0f"
)
REHEARSAL_IMAGE = (
    "ghcr.io/jkershawrh/agentic-ai-101-rehearsal@"
    "sha256:7839278c27a1960f425e37dbe3a8c4479d61c866727207976446120686bf3e63"
)


def test_agentic_ai_101_intake_is_an_internal_draft_with_exact_artifacts() -> None:
    intake = load_intake(INTAKE_PATH)

    report = validate_intake(intake)
    assert report["validation_status"] == "pass"
    assert report["errors"] == []
    assert intake["catalog"]["status"] == "draft"
    assert intake["learning"]["learning_level"] == "101"
    assert intake["learning"]["recommended_next_items"] == [
        "intel-xeon6-agent-201"
    ]
    assert intake["runtime"]["allowed_exposure_policies"] == ["internal"]
    assert intake["runtime"]["required_models"] == []
    assert intake["runtime"]["workload"]["helm_values"] == {
        "workload_image": REHEARSAL_IMAGE,
        "presentation_image": PRESENTATION_IMAGE,
        "source_state": "REHEARSAL",
    }


def test_agentic_ai_101_one_seat_contract_is_fail_closed() -> None:
    intake = load_intake(INTAKE_PATH)
    contract = load_certification_contract(CONTRACT_PATH)

    assert validate_certification_contract(
        contract,
        intake=intake,
        repo_root=ROOT,
        contract_path=CONTRACT_PATH,
    ) == []
    assert contract["spec"]["target_cluster"] == "flightpath"
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [
        1
    ]
    assertions = {
        assertion["path"]: assertion.get("equals")
        for assertion in contract["spec"]["seat_probe"]["json_assertions"]
    }
    assert assertions["workflow.state_change_denied"] is True
    assert assertions["workflow.target_mutated"] is False
    assert assertions["authority.human_review_required"] is True


def test_agentic_ai_101_probe_checks_isolation_and_never_claims_live_inference() -> None:
    probe = PROBE_PATH.read_text()

    assert "source_state: \"REHEARSAL\"" in probe
    assert "inference: {required: false, participated: false}" in probe
    assert "policyDecision == \"deny and escalate\"" in probe
    assert "targetMutated == false" in probe
    assert "cross_namespace=DENIED" in probe
    assert "node_list=DENIED" in probe
