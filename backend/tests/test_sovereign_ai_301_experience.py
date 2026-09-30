from pathlib import Path

import yaml

from app.services.catalog_onboarding import build_catalog_item, load_intake


ROOT = Path(__file__).resolve().parents[2]


def _load(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_sovereign_ai_301_is_terminal_scoped_and_allocates_no_model_access() -> None:
    catalog = _load("catalog/sovereign-ai-301/catalog-item.yaml")
    intake = _load("catalog-onboarding/sovereign-ai-301.yaml")
    contract = _load("certification/catalog/sovereign-ai-301.yaml")
    review = _load("evidence/lab-experience-review-20260930.yaml")["labs"][
        "sovereign-ai-301"
    ]

    metadata = catalog["metadata"]
    runtime = intake["runtime"]

    assert catalog == build_catalog_item(load_intake(ROOT / "catalog-onboarding/sovereign-ai-301.yaml"))
    assert catalog["status"] == "draft"
    assert metadata["certification_stage"] == "immutable-source-published"
    assert metadata["certification_transfer"] == "none"
    assert metadata["recommended_next_items"] == ["sovereign-ai-401"]
    assert metadata["required_models"] == runtime["required_models"] == []
    assert metadata["inference_endpoint"] == runtime["inference_endpoint"] == "none"
    assert catalog["validation_refs"] == runtime["validation_refs"] == [
        "pod-ready",
        "route-accessible",
    ]
    assert metadata["workload_runtime_secret_name"] == ""
    assert metadata["workload_runtime_secret_sources"] == {}
    assert runtime["workload"]["runtime_secret_name"] == ""
    assert runtime["workload"]["runtime_secret_sources"] == {}
    expected_gitops_repo = "git@github.com:jkershawrh/sovereign-ai-301.git"
    expected_revision = "958cbdfc08582aff0a5db2a273cd212ef270d88c"
    assert metadata["showroom_content_repo_url"] == expected_gitops_repo
    assert metadata["workload_repo"] == expected_gitops_repo
    assert intake["sources"]["showroom"]["gitops_repo_url"] == expected_gitops_repo
    assert intake["sources"]["workload"]["gitops_repo_url"] == expected_gitops_repo
    assert metadata["showroom_content_ref"] == expected_revision
    assert metadata["workload_revision"] == expected_revision
    assert review["source_state"]["catalog_pinned_revision"] == expected_revision
    assert metadata["workload_routes"] == runtime["workload"]["routes"] == {
        "ui": "story"
    }
    assert "get route story" in (ROOT / "scripts/certify-sovereign-ai-301-seat.sh").read_text()

    expected_tabs = ["story", "terminal"]
    assert [tab["id"] for tab in metadata["showroom_tabs"]] == expected_tabs
    assert [tab["id"] for tab in runtime["tabs"]] == expected_tabs
    assert "Console" not in review["operators"]["evidence"]
    assert "Console" not in review["next_action"]
    assert "Terminal" in review["operators"]["evidence"]
    assert "Terminal" in review["next_action"]
    assert review["source_state"]["certification_target"] == "truthful-rehearsal-only"
    assert review["source_state"]["live_confidentiality_claims"] == "prohibited"

    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "journey.model_invoked", "equals": False} in assertions
    assert {"path": "journey.confidential_runtime_enabled", "equals": False} in assertions
    assert {"path": "journey.hardware_quote_verified", "equals": False} in assertions
    assert {"path": "journey.trustee_verified", "equals": False} in assertions
    assert {"path": "journey.inference_authorized", "equals": False} in assertions
    assert any(item["path"] == "terminal_scope" for item in assertions)


def test_sovereign_ai_301_rehearsal_proof_cannot_transfer_to_live_tdx() -> None:
    catalog = _load("catalog/sovereign-ai-301/catalog-item.yaml")
    contract = _load("certification/catalog/sovereign-ai-301.yaml")

    values = catalog["metadata"]["workload_helm_values"]
    assert values["source_state"] == "REHEARSAL"
    assert values["confidential_runtime_enabled"] is False
    assert values["live_tdx_claimed"] is False
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    for expected in (
        {"path": "journey.mode", "equals": "REHEARSAL"},
        {"path": "journey.live_tdx_observed", "equals": False},
        {"path": "journey.synthetic_receipt_only", "equals": True},
        {"path": "journey.key_material_released", "equals": False},
        {"path": "journey.model_invoked", "equals": False},
        {"path": "journey.confidential_runtime_enabled", "equals": False},
        {"path": "journey.hardware_quote_verified", "equals": False},
        {"path": "journey.trustee_verified", "equals": False},
        {"path": "journey.inference_authorized", "equals": False},
    ):
        assert expected in assertions

    assert catalog["metadata"]["activation_blockers"] == [
        "Complete exact one-seat Flightpath rehearsal certification, reclaim, credential-revocation observation, and zero-residue proof before activation."
    ]
