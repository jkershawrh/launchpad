from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/agentic-ai-601/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/agentic-ai-601.yaml"
CERTIFICATION = ROOT / "certification/catalog/agentic-ai-601.yaml"
SEAT_PROBE = ROOT / "scripts/certify-agentic-ai-601-seat.sh"
REVISION = "de4bc2ea057fce33967b2eb52790d57b77ff0832"
PRESENTATION_DIGEST = "sha256:9395648031e9e7d9b33985b550cb06133f1e11464f086a4dea34bbfd63ecadf1"
QUALIFIER_DIGEST = "sha256:b95d3779c254a352028cdfb13aecffb229113ef78d2dba332aef19596ca0d732"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_agentic_601_exact_release_and_factory_receipt_are_consistent():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    metadata = catalog["metadata"]

    assert intake["sources"]["showroom"]["revision"] == REVISION
    assert intake["sources"]["workload"]["revision"] == REVISION
    assert intake["factory_receipt"]["source_revision"] == REVISION
    assert intake["factory_receipt"]["artifact_source_revision"] == REVISION
    assert metadata["showroom_content_ref"] == REVISION
    assert metadata["workload_revision"] == REVISION
    assert metadata["source_content_revision"] == REVISION
    assert metadata["workload_helm_values"]["images"] == {
        "presentation": {
            "repository": "ghcr.io/jkershawrh/agentic-ai-601-presentation",
            "digest": PRESENTATION_DIGEST,
        },
        "qualifier": {
            "repository": "ghcr.io/jkershawrh/agentic-ai-601-qualifier",
            "digest": QUALIFIER_DIGEST,
        },
    }
    assert intake["runtime"]["workload"]["helm_values"]["images"] == metadata[
        "workload_helm_values"
    ]["images"]


def test_agentic_601_is_truthfully_active_for_one_seat_internal_rehearsal():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    certification = _load(CERTIFICATION)
    metadata = catalog["metadata"]

    assert catalog["status"] == "active"
    assert intake["certification"]["certified_seats"] == 1
    assert intake["certification"]["stage"] == "one-seat-destination-qualified"
    assert metadata["certification_stage"] == "one-seat-destination-qualified"
    assert intake["certification"]["max_workshop_seats"] == 1
    assert metadata["max_workshop_seats"] == 1
    assert metadata["promotion_sequence"] == [1]
    assert intake["certification"]["promotion_sequence"] == [1]
    assert metadata["required_models"] == []
    assert metadata["inference_endpoint"] == "none"
    assert metadata["workload_helm_values"]["qualifier"] == {
        "sourceState": "rehearsal",
        "authorityExecutionEnabled": False,
    }
    assert certification["spec"]["state"] == "destination-qualification"
    assert certification["spec"]["execution_enabled"] is True
    assert certification["spec"]["execution_blockers"]
    assert [profile["seats"] for profile in certification["spec"]["scale_profiles"]] == [1]
    assert metadata["activation_blockers"] == []
    assert metadata["production_blockers"]
    assert intake["certification"]["activation_blockers"] == []
    assert intake["certification"]["production_blockers"]
    assert intake["factory_receipt"]["orderable"] is True
    assert intake["factory_receipt"]["certified"] is True
    assert intake["factory_receipt"]["promotion_eligible"] is False


def test_agentic_601_operator_tabs_are_explicit():
    intake = _load(INTAKE)
    assert [tab["id"] for tab in intake["runtime"]["tabs"]] == [
        "story",
        "terminal",
        "qualification",
        "openshift-console",
    ]
    qualification = next(
        tab for tab in intake["runtime"]["tabs"] if tab["id"] == "qualification"
    )
    assert qualification["path"] == "/api/v1/status/view"


def test_agentic_601_rubric_uses_only_certification_runner_gates():
    certification = _load(CERTIFICATION)
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


def test_agentic_601_certification_receipt_proves_no_inference_or_target_mutation():
    certification = _load(CERTIFICATION)
    assertions = {
        (item["path"], item["equals"])
        for item in certification["spec"]["seat_probe"]["json_assertions"]
        if "equals" in item
    }
    probe = SEAT_PROBE.read_text()

    assert ("inference.required", False) in assertions
    assert ("inference.participated", False) in assertions
    assert ("rehearsal.target_state_mutated", False) in assertions
    assert 'inference: {required: false, participated: false}' in probe
    assert 'rehearsal: {target_state_mutated: false}' in probe
    assert "curl_options=(-fsS" in probe
    assert "curl_options=(-fsSk" not in probe
    assert ("provenance.source_revision", REVISION) in assertions
    assert ("runtime_images.presentation", f"ghcr.io/jkershawrh/agentic-ai-601-presentation@{PRESENTATION_DIGEST}") in assertions
    assert ("runtime_images.qualifier", f"ghcr.io/jkershawrh/agentic-ai-601-qualifier@{QUALIFIER_DIGEST}") in assertions


def test_agentic_601_certification_walks_every_showroom_stage():
    certification = _load(CERTIFICATION)
    pages = certification["spec"]["showroom"]["pages"]
    assert [page["id"] for page in pages] == [
        "welcome",
        "preflight",
        "signal",
        "decision",
        "authority",
        "bounded-action",
        "validate-rollback",
        "learn-evaluate",
        "close-handoff",
    ]
    assert [page["path"] for page in pages] == [
        "/www/agentic-ai-601/index.html",
        "/www/agentic-ai-601/00-preflight.html",
        "/www/agentic-ai-601/01-signal.html",
        "/www/agentic-ai-601/02-decision.html",
        "/www/agentic-ai-601/03-authority.html",
        "/www/agentic-ai-601/04-bounded-action.html",
        "/www/agentic-ai-601/05-validate-rollback.html",
        "/www/agentic-ai-601/06-learn-evaluate.html",
        "/www/agentic-ai-601/07-close-handoff.html",
    ]


def test_agentic_601_probe_matches_the_qualifier_readiness_contract():
    probe = SEAT_PROBE.read_text()
    assert "${api}/readyz" in probe
    assert "'.status == \"ok\"'" in probe
    assert 'single_use_human_approval_required' in probe
    assert '"${api}/api/v1/status"' in probe
    assert '"${api}/api/v1/status/view"' in probe
    assert "AGENTIC AI 601 · EARNED AUTHORITY" in probe
    assert "Qualification Evidence" in probe
    assert "Human review required" in probe
    assert "No production authority" in probe
