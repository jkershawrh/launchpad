from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
REVISION = "1eafe62582e6a4b15d8ec1b575c72b72e873b996"


def _load(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_sovereign_ai_501_rehearses_fleet_qualification_without_live_claims() -> None:
    catalog = _load("catalog/sovereign-ai-501/catalog-item.yaml")
    intake = _load("catalog-onboarding/sovereign-ai-501.yaml")
    contract = _load("certification/catalog/sovereign-ai-501.yaml")

    metadata = catalog["metadata"]
    runtime = intake["runtime"]

    assert metadata["showroom_content_ref"] == REVISION
    assert metadata["source_content_revision"] == REVISION
    assert metadata["workload_revision"] == REVISION
    assert intake["sources"]["showroom"]["revision"] == REVISION
    assert intake["sources"]["workload"]["revision"] == REVISION
    assert intake["sources"]["showroom"]["gitops_repo_url"].startswith("https://")
    assert intake["sources"]["workload"]["gitops_repo_url"].startswith("https://")
    assert catalog["required_capabilities"] == runtime["required_capabilities"] == [
        "openshift",
        "showroom",
    ]

    assert metadata["required_models"] == runtime["required_models"] == []
    assert metadata["inference_endpoint"] == runtime["inference_endpoint"] == "none"
    assert "inference-health" not in catalog["validation_refs"]
    assert metadata["workload_runtime_secret_name"] == ""
    assert metadata["workload_runtime_secret_sources"] == {}
    assert runtime["workload"]["runtime_secret_name"] == ""
    assert runtime["workload"]["runtime_secret_sources"] == {}

    expected_tabs = ["story", "terminal", "qualification", "openshift-console"]
    assert [tab["id"] for tab in metadata["showroom_tabs"]] == expected_tabs
    assert [tab["id"] for tab in runtime["tabs"]] == expected_tabs
    assert runtime["tabs"][0]["source"] == "workload.route.ui"
    assert runtime["tabs"][2]["source"] == "workload.route.qualification"
    assert runtime["workload"]["routes"] == {"ui": "story", "qualification": "fleet"}

    values = metadata["workload_helm_values"]
    assert values["source_state"] == "REHEARSAL"
    assert values["confidential_runtime_enabled"] is False
    assert values["live_tdx_claimed"] is False
    assert values["images"]["presentation"]["digest"] == (
        "sha256:350f4cd7a612469f4e8ab94722d083b08436d1b6357e08b42b0d57bbe98f631b"
    )
    assert values["images"]["qualifier"]["digest"] == (
        "sha256:90b243358b5bd21cdeb461a5402baf068ec4270dd8b6828687ffb3ae04bc592d"
    )

    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    for expected in (
        {"path": "journey.mode", "equals": "REHEARSAL"},
        {"path": "journey.live_fleet_observed", "equals": False},
        {"path": "journey.live_capacity_measured", "equals": False},
        {"path": "journey.protected_resources_released", "equals": 0},
        {"path": "journey.model_executions", "equals": 0},
        {"path": "readiness.presentation_restarts", "equals": 0},
        {"path": "operator_journey.terminal_scope_verified", "equals": True},
        {"path": "operator_journey.console_url_present", "equals": True},
        {"path": "operator_journey.qualification_service_verified", "equals": True},
    ):
        assert expected in assertions
    assert any(item["path"] == "terminal_scope" for item in assertions)

    certifier = (ROOT / "scripts/certify-sovereign-ai-501-seat.sh").read_text(
        encoding="utf-8"
    )
    assert "get route story" in certifier
    assert "get route sovereign-ai-501-presentation" not in certifier
    assert "curl -k" not in certifier
    assert "curl -sk" not in certifier
    assert "curl -sSk" not in certifier
    assert "whoami --show-console" in certifier
