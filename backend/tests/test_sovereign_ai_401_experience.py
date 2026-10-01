from pathlib import Path

import yaml

from app.services.catalog_onboarding import build_catalog_item, load_intake


ROOT = Path(__file__).resolve().parents[2]
REVISION = "0a528c651c2cb6b6bb9d31875aa2ada099dedd35"


def _load(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_sovereign_ai_401_exposes_operations_without_allocating_model_access() -> None:
    catalog = _load("catalog/sovereign-ai-401/catalog-item.yaml")
    intake = _load("catalog-onboarding/sovereign-ai-401.yaml")
    contract = _load("certification/catalog/sovereign-ai-401.yaml")

    metadata = catalog["metadata"]
    runtime = intake["runtime"]

    assert catalog == build_catalog_item(load_intake(ROOT / "catalog-onboarding/sovereign-ai-401.yaml"))
    assert metadata["showroom_content_ref"] == REVISION
    assert metadata["source_content_revision"] == REVISION
    assert metadata["workload_revision"] == REVISION
    assert intake["sources"]["showroom"]["revision"] == REVISION
    assert intake["sources"]["workload"]["revision"] == REVISION
    assert catalog["status"] == "draft"
    assert metadata["certification_stage"] == "immutable-source-published"
    assert metadata["certification_transfer"] == "none"
    assert metadata["required_models"] == runtime["required_models"] == []
    assert catalog["required_capabilities"] == runtime["required_capabilities"] == [
        "openshift",
        "showroom",
    ]
    assert metadata["inference_endpoint"] == runtime["inference_endpoint"] == "none"
    assert catalog["validation_refs"] == runtime["validation_refs"] == [
        "pod-ready",
        "route-accessible",
    ]
    assert metadata["workload_runtime_secret_name"] == ""
    assert metadata["workload_runtime_secret_sources"] == {}
    assert runtime["workload"]["runtime_secret_name"] == ""
    assert runtime["workload"]["runtime_secret_sources"] == {}
    assert runtime["workload"]["routes"]["ui"] == "story"

    expected_tabs = ["story", "terminal", "qualification", "openshift-console"]
    assert [tab["id"] for tab in metadata["showroom_tabs"]] == expected_tabs
    assert [tab["id"] for tab in runtime["tabs"]] == expected_tabs
    assert runtime["tabs"][0]["source"] == "workload.route.ui"

    values = metadata["workload_helm_values"]
    assert values["source_state"] == "REHEARSAL"
    assert values["confidential_runtime_enabled"] is False
    assert values["live_tdx_claimed"] is False
    assert values["images"]["presentation"]["digest"] == (
        "sha256:9e980f5113f340edf209acfa8572a273c1d5220a79165f7e6379ecd3fd0e1df4"
    )
    assert values["images"]["qualifier"]["digest"] == (
        "sha256:df3fe53d316198a76f4fb526cf2e10be51ef9a14c97a46ea5de29e8f38b65a50"
    )

    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    for expected in (
        {"path": "readiness.presentation_restarts", "equals": 0},
        {"path": "journey.mode", "equals": "REHEARSAL"},
        {"path": "journey.live_tdx_observed", "equals": False},
        {"path": "journey.key_material_released", "equals": False},
        {"path": "journey.model_invoked", "equals": False},
        {"path": "operator_journey.terminal_scope_verified", "equals": True},
        {"path": "operator_journey.console_url_present", "equals": True},
        {"path": "operator_journey.qualification_service_verified", "equals": True},
    ):
        assert expected in assertions
    assert any(item["path"] == "terminal_scope" for item in assertions)

    certifier = (ROOT / "scripts/certify-sovereign-ai-401-seat.sh").read_text(
        encoding="utf-8"
    )
    assert "curl -k" not in certifier
    assert "curl -sk" not in certifier
    assert "curl -sSk" not in certifier
    assert "whoami --show-console" in certifier
