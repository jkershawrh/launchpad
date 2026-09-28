from pathlib import Path

import yaml

from app.services.catalog_certification import (
    load_certification_contract,
    validate_certification_contract,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_DRIVER = ROOT / "scripts/certify-multi-agent-seat.sh"
OPERATIONS_DRIVER = ROOT / "scripts/certify-operate-agentic-blueprint-seat.sh"
CERTIFICATION = ROOT / "certification/catalog/operate-agentic-blueprint.yaml"


def test_operations_driver_selects_401_contract_without_duplicating_runtime_probe():
    source = OPERATIONS_DRIVER.read_text()

    assert 'SHOWROOM_MARKER="Operate Evidence-Backed Multi-Agent Systems"' in source
    assert "PRESENTATION_REQUIRED=true" in source
    assert 'exec "$script_dir/certify-multi-agent-seat.sh" "$@"' in source


def test_shared_driver_proves_the_live_presentation_and_policy_proxy():
    source = BASE_DRIVER.read_text()

    assert "PRESENTATION_REQUIRED" in source
    assert "agentic-operations-presentation" in source
    assert '"https://${presentation_host}/api/v1/policy"' in source
    assert '"https://${presentation_host}/health"' in source
    assert '"https://${presentation_host}/lab"' in source
    assert '"https://${presentation_host}/api/v1/workflow"' in source
    assert '.authority == "recommend_only"' in source
    assert 'presentation: $presentation' in source


def test_shared_driver_keeps_301_behavior_as_the_default():
    source = BASE_DRIVER.read_text()

    assert 'SHOWROOM_MARKER:-Build Multi-Agent AI Systems' in source
    assert 'PRESENTATION_REQUIRED:-false' in source


def test_401_certification_is_one_seat_flightpath_and_requires_live_presentation():
    contract = load_certification_contract(CERTIFICATION)
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
        }
    ]
    assert spec["seat_probe"]["argv"][1] == (
        "scripts/certify-operate-agentic-blueprint-seat.sh"
    )
    assertions = {
        item["path"]: item for item in spec["seat_probe"]["json_assertions"]
    }
    assert assertions["presentation.required"]["equals"] is True
    assert assertions["presentation.policy.authority"]["equals"] == "recommend_only"
    assert assertions["presentation.client_token_exposed"]["equals"] is False
    assert assertions["presentation.navigation_markers"]["equals"] == 5
    assert assertions["presentation.handoff.http_status"]["equals"] == 302
    assert assertions["presentation.workflow.errors"]["equals"] == 0
    assert assertions["intel_xeon_inference.configured_model"]["equals"] == (
        "granite-3.2-8b-tools"
    )
