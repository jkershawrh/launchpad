from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/agent-reliability/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/agent-reliability.yaml"
CERTIFICATION = ROOT / "certification/catalog/agent-reliability.yaml"
CERTIFIER = ROOT / "scripts/certify-agent-reliability-seat.sh"
REVIEW_EVIDENCE = ROOT / "evidence/lab-experience-review-20260930.yaml"
REVISION = "fa6a1797662e10eced38cc3cfd5fee4f52ecc7fc"
DIGEST = "sha256:eca79307a3a23e9314bd050a8f944f00a88f2869f55b24c925551b545984dc00"
IMAGE_SOURCE_REVISION = REVISION
IMAGE_REFERENCE = f"ghcr.io/jkershawrh/agent-reliability-quickstart@{DIGEST}"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_agent_reliability_canonical_mapping_and_immutable_pins_are_exact():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    metadata = catalog["metadata"]

    assert catalog["catalog_item_id"] == "agent-reliability"
    assert intake["catalog"]["catalog_item_id"] == "agent-reliability"
    assert metadata["showroom_content_repo_url"].endswith(
        "/agent-reliability-quickstart.git"
    )
    assert metadata["showroom_content_ref"] == REVISION
    assert metadata["workload_revision"] == REVISION
    assert metadata["source_content_revision"] == REVISION
    assert intake["sources"]["showroom"]["revision"] == REVISION
    assert intake["sources"]["workload"]["revision"] == REVISION
    assert metadata["workload_helm_values"]["image"]["digest"] == DIGEST
    assert intake["runtime"]["workload"]["helm_values"]["image"]["digest"] == DIGEST
    assert metadata["workload_image_source_revision"] == IMAGE_SOURCE_REVISION
    assert intake["runtime"]["workload"]["image_source_revision"] == IMAGE_SOURCE_REVISION


def test_agent_reliability_remains_a_one_seat_exact_image_draft():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)

    assert catalog["status"] == "draft"
    assert intake["catalog"]["status"] == "draft"
    assert catalog["metadata"]["max_workshop_seats"] == 1
    assert intake["certification"]["max_workshop_seats"] == 1
    assert intake["certification"]["promotion_sequence"] == [1]
    assert intake["certification"]["stage"] == "exact-image-published"
    blockers = " ".join(intake["certification"]["activation_blockers"])
    assert "Recertify one Flightpath seat against the exact source and image revisions" in blockers
    assert intake["runtime"]["required_models"] == ["granite-3.2-8b-tools"]
    assert intake["runtime"]["inference_endpoint"] == "litellm_virtual_key_candidate"


def test_agent_reliability_operator_tabs_are_explicit():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    assert [tab["id"] for tab in intake["runtime"]["tabs"]] == [
        "terminal",
        "workspace",
        "openshift-console",
    ]
    assert [tab["title"] for tab in intake["runtime"]["tabs"]] == [
        "Terminal",
        "Reliability Advisor",
        "OpenShift Console",
    ]
    assert intake["quality"]["showroom"]["execute_block_count"] == 33
    assert catalog["metadata"]["intake_quality"]["showroom"]["execute_block_count"] == 33


def test_agent_reliability_certification_proves_remote_model_participation():
    contract = _load(CERTIFICATION)
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1]
    assertions = {
        (item["path"], item.get("equals"))
        for item in contract["spec"]["seat_probe"]["json_assertions"]
    }
    assert ("reliability_journey.inference_provider", "openai-compatible") in assertions
    assert ("reliability_journey.configured_model", "granite-3.2-8b-tools") in assertions
    assert ("reliability_journey.observed_model", "granite-3.2-8b-tools") in assertions
    assert ("reliability_journey.model_participated", True) in assertions
    assert ("runtime.workload_image", IMAGE_REFERENCE) in assertions

    certifier = CERTIFIER.read_text()
    assert '.inference_provider == "openai-compatible"' in certifier
    assert '.configured_model == "granite-3.2-8b-tools"' in certifier
    assert ".observed_model == .configured_model" in certifier
    assert ".model_participated == true" in certifier
    assert IMAGE_REFERENCE in certifier


def test_agent_reliability_evidence_records_exact_candidate_boundary():
    review = _load(REVIEW_EVIDENCE)["labs"]["agent-reliability"]
    provenance = review["source_state"]["image_provenance"]

    assert provenance["manifest_digest"] == DIGEST
    assert provenance["image_source_revision"] == IMAGE_SOURCE_REVISION
    assert review["source_state"]["catalog_pinned_revision"] == REVISION
    assert "fixable Critical" in review["source_state"]["publication_note"]
    assert "one fresh Flightpath seat" in review["next_action"]
