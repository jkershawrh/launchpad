from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVISION = "6d7c6f267407d42ca465b8a381d841d8b5b77567"
PRESENTATION = "sha256:c9301b53eca8b8a20c9f87d142363b7c9b0f2abffeb36fd6b97ee3ebb895ec2d"
REHEARSAL = "sha256:c7f5058213960ceb1a268506f43fe666c4cf5df62ce7d6e444dd277b34886958"


def _load(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_sovereign_ai_101_orderability_matches_exact_rehearsal_proof() -> None:
    catalog = _load("catalog/sovereign-ai-101/catalog-item.yaml")
    intake = _load("catalog-onboarding/sovereign-ai-101.yaml")
    contract = _load("certification/catalog/sovereign-ai-101.yaml")

    metadata = catalog["metadata"]
    runtime = intake["runtime"]
    certification = intake["certification"]

    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert metadata["certification_stage"] == certification["stage"] == "1-seat-certified"
    assert metadata["max_workshop_seats"] == certification["max_workshop_seats"] == 1
    assert metadata["activation_blockers"] == certification["activation_blockers"] == []
    assert metadata["allowed_exposure_policies"] == ["internal", "public_code"]
    assert runtime["allowed_exposure_policies"] == ["internal", "public_code"]

    assert metadata["required_models"] == runtime["required_models"] == []
    assert metadata["inference_endpoint"] == runtime["inference_endpoint"] == "none"
    assert "inference-health" not in catalog["validation_refs"]
    assert metadata["workload_runtime_secret_name"] == ""
    assert metadata["workload_runtime_secret_sources"] == {}
    assert runtime["workload"]["runtime_secret_name"] == ""
    assert runtime["workload"]["runtime_secret_sources"] == {}

    expected_tabs = ["story", "terminal", "openshift-console"]
    assert [tab["id"] for tab in metadata["showroom_tabs"]] == expected_tabs
    assert [tab["id"] for tab in runtime["tabs"]] == expected_tabs

    assert metadata["showroom_content_ref"] == SOURCE_REVISION
    assert metadata["workload_revision"] == SOURCE_REVISION
    assert intake["sources"]["showroom"]["revision"] == SOURCE_REVISION
    assert intake["sources"]["workload"]["revision"] == SOURCE_REVISION
    assert PRESENTATION in metadata["workload_helm_values"]["presentation_image"]
    assert REHEARSAL in metadata["workload_helm_values"]["workload_image"]

    scope = " ".join(certification["certification_scope"])
    assert "does not transfer" not in scope
    assert "exact immutable revision" in scope

    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "journey.mode", "equals": "REHEARSAL"} in assertions
    assert {"path": "journey.live_qualified", "equals": False} in assertions
    assert {"path": "journey.session_removed", "equals": True} in assertions
    assert {"path": "operators.openshift_console_url_declared", "equals": True} in assertions
    assert any(item["path"] == "terminal_scope" for item in assertions)

    probe = (ROOT / "scripts/certify-sovereign-ai-101-seat.sh").read_text()
    assert "curl_options=(-sS" in probe
    assert "curl_options=(-sSk" not in probe
    assert "OpenShift Console" in probe
