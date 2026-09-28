from pathlib import Path

import yaml

from app.services.catalog_certification import (
    build_certification_plan,
    load_certification_contract,
    validate_certification_contract,
)
from app.services.catalog_onboarding import load_intake


ROOT = Path(__file__).resolve().parents[2]
BASE_DRIVER = ROOT / "scripts/certify-multi-agent-seat.sh"
OPERATIONS_DRIVER = ROOT / "scripts/certify-operate-agentic-blueprint-seat.sh"
CERTIFICATION = ROOT / "certification/catalog/operate-agentic-blueprint.yaml"
INTAKE = ROOT / "catalog-onboarding/operate-agentic-blueprint.yaml"


def test_operations_driver_selects_401_contract_without_duplicating_runtime_probe():
    source = OPERATIONS_DRIVER.read_text()

    assert 'SHOWROOM_MARKER="Operate Evidence-Backed Multi-Agent Systems"' in source
    assert "PRESENTATION_REQUIRED=true" in source
    assert 'exec "$script_dir/certify-multi-agent-seat.sh" "$@"' in source


def test_shared_driver_proves_live_presentation_and_policy_endpoint():
    source = BASE_DRIVER.read_text()

    assert "PRESENTATION_REQUIRED" in source
    assert "oc get route story" in source
    assert '"https://${presentation_host}/api/v1/policy"' in source
    assert '"https://${presentation_host}/health"' in source
    assert '"https://${presentation_host}/lab"' in source
    assert '"https://${presentation_host}/api/v1/workflow"' in source
    assert 'stage="presentation-navigation-bundle"' in source
    assert 'stage="presentation-mode-labels"' in source
    assert 'stage="presentation-live-policy"' in source
    assert '[[ "$presentation_policy_http_status" == "200" ]]' in source
    assert '.authority == "recommend_only"' in source
    assert 'presented_as_live: true' in source
    assert 'presentation: $presentation' in source


def test_shared_driver_keeps_301_behavior_as_the_default():
    source = BASE_DRIVER.read_text()

    assert 'SHOWROOM_MARKER:-Build Multi-Agent AI Systems' in source
    assert 'PRESENTATION_REQUIRED:-false' in source


def test_shared_driver_retries_terminal_scope_during_concurrent_certification():
    source = BASE_DRIVER.read_text()

    assert 'for terminal_scope_attempt in {1..6}; do' in source
    assert 'terminal_scope_valid=true' in source
    assert 'sleep "$((terminal_scope_attempt * 2))"' in source
    assert '[[ "$terminal_scope_valid" == "true" ]]' in source


def test_401_certification_records_the_earned_twenty_five_seat_limit():
    contract = load_certification_contract(CERTIFICATION)
    intake = load_intake(INTAKE)
    assert validate_certification_contract(
        contract,
        repo_root=ROOT,
        contract_path=CERTIFICATION,
    ) == []
    spec = contract["spec"]

    assert spec["target_cluster"] == "flightpath"
    assert spec["allowed_exposure_policies"] == ["internal"]
    assert spec["scale_profiles"] == [
        {
            "seats": 1,
            "required_consecutive_runs": 1,
            "probe_concurrency": 1,
            "maximum_ready_seconds": 900,
            "maximum_cleanup_seconds": 600,
        },
        {
            "seats": 5,
            "required_consecutive_runs": 1,
            "probe_concurrency": 5,
            "maximum_ready_seconds": 1200,
            "maximum_cleanup_seconds": 900,
        },
        {
            "seats": 25,
            "required_consecutive_runs": 3,
            "probe_concurrency": 10,
            "maximum_ready_seconds": 2400,
            "maximum_cleanup_seconds": 1200,
        },
    ]
    assert spec["seat_probe"]["argv"][1] == (
        "scripts/certify-operate-agentic-blueprint-seat.sh"
    )
    plan = build_certification_plan(
        contract,
        intake=intake,
        seats=5,
        exposure_policy="internal",
    )
    assert plan["current_certified_seats"] == 1
    assert plan["next_promotion_target"] == 5
    assert plan["certification_override"] is True
    assert plan["execution_eligible"] is True
    assert plan["probe_concurrency"] == 5
    assert plan["required_consecutive_runs"] == 1
    assertions = {
        item["path"]: item for item in spec["seat_probe"]["json_assertions"]
    }
    assert assertions["presentation.required"]["equals"] is True
    assert assertions["presentation.policy.mode"]["equals"] == "live"
    assert assertions["presentation.policy.endpoint_http_status"]["equals"] == 200
    assert assertions["presentation.policy.authority"]["equals"] == "recommend_only"
    assert assertions["presentation.policy.presented_as_live"]["equals"] is True
    assert assertions["presentation.client_token_exposed"]["equals"] is False
    assert assertions["presentation.navigation_markers"]["equals"] == 5
    assert assertions["presentation.handoff.http_status"]["equals"] == 302
    assert assertions["presentation.workflow.errors"]["equals"] == 0
    assert assertions["correlation.fields_present"]["equals"] is True
    assert assertions["correlation.stable"]["equals"] is True
    assert assertions["correlation.unique_event_ids"]["equals"] is True
    assert assertions["correlation.response_matches"]["equals"] is True
    assert assertions["intel_xeon_inference.configured_model"]["equals"] == (
        "granite-3.2-8b-tools"
    )
