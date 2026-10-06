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
    "sha256:8fc499945efa777483c125dbc691d0ed89cc8140c9a0c63fec268add52362856"
)
REHEARSAL_IMAGE = (
    "ghcr.io/jkershawrh/agentic-ai-101-rehearsal@"
    "sha256:69af3304d5b639871787dfc63ffd5961b7d4473c9228d7d4ede55f8ef2e49fb3"
)


def test_agentic_ai_101_is_one_seat_certified_for_internal_and_public_access() -> None:
    intake = load_intake(INTAKE_PATH)

    report = validate_intake(intake)
    assert report["validation_status"] == "pass"
    assert report["errors"] == []
    assert intake["catalog"]["status"] == "active"
    assert intake["certification"]["stage"] == "1-seat-certified"
    assert intake["certification"]["certified_seats"] == 1
    assert intake["certification"]["activation_blockers"] == []
    assert intake["learning"]["learning_level"] == "101"
    assert intake["learning"]["recommended_next_items"] == [
        "intel-xeon6-agent-201"
    ]
    assert intake["runtime"]["allowed_exposure_policies"] == [
        "internal",
        "public_code",
    ]
    assert intake["runtime"]["required_models"] == []
    assert intake["runtime"]["tabs"] == [
        {
            "id": "story",
            "title": "Interactive Story",
            "source": "workload.route.presentation",
            "path": "/story/",
            "same_origin_path": "/story/",
            "rewrite_target": "/",
            "public_proxy_root": True,
        },
        {
            "id": "terminal",
            "title": "Terminal",
            "source": "showroom.terminal",
        },
        {
            "id": "openshift-console",
            "title": "OpenShift Console",
            "source": "cluster.console_url",
        },
    ]
    assert intake["runtime"]["workload"]["helm_values"] == {
        "workload_image": REHEARSAL_IMAGE,
        "presentation_image": PRESENTATION_IMAGE,
        "source_state": "REHEARSAL",
    }
    assert intake["runtime"]["workload"]["kustomize_images"] == [
        "ghcr.io/jkershawrh/agentic-ai-101-rehearsal=" + REHEARSAL_IMAGE,
        "ghcr.io/jkershawrh/agentic-ai-101-presentation=" + PRESENTATION_IMAGE,
    ]


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
    assert 'curl -fksS --retry 4' in probe
    assert 'stage="showroom-runtime-connectivity"' in probe
    assert "http://agentic-ai-101:8080/readyz" in probe
    assert "showroom_to_runtime: true" in probe


def test_agentic_ai_101_probe_fails_closed_on_runtime_image_drift() -> None:
    probe = PROBE_PATH.read_text()

    assert "require_exact_image" in probe
    assert 'require_exact_image "presentation"' in probe
    assert 'require_exact_image "rehearsal"' in probe
    assert 'return 1' in probe
    assert '[[ "$presentation_image" == "$expected_presentation_image" ]]' not in probe
    assert '[[ "$rehearsal_image" == "$expected_rehearsal_image" ]]' not in probe
