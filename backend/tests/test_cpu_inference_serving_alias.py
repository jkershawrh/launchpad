import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/cpu-inference-serving/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/cpu-inference-serving.yaml"
CERTIFICATION = ROOT / "certification/catalog/cpu-inference-serving.yaml"
CANONICAL = ROOT / "catalog/intel-llm-cpu-serving/catalog-item.yaml"
VISIBILITY = ROOT / "frontend/src/catalogVisibility.ts"
EVIDENCE = (
    ROOT
    / "evidence/runs/staging-candidate-e2d78de/flightpath-e2d78de-20260929T124528Z-7fpm8-cpu-inference-serving-five-seat.json"
)
CONTENT_REVISION = "9526ede61b5c31949f3a1bedd133b5a17e554178"
WORKLOAD_REVISION = "88867e14b1eede7d9aa563069aa093c122a4a53a"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_cpu_inference_serving_is_a_hidden_compatibility_alias():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    metadata = catalog["metadata"]

    assert metadata["migration_mode"] == "compatibility_alias"
    assert metadata["canonical_item_id"] == "intel-llm-cpu-serving"
    assert intake["runtime"]["compatibility_alias_of"] == "intel-llm-cpu-serving"
    assert "migration_mode !== 'compatibility_alias'" in VISIBILITY.read_text()
    assert catalog["status"] == "active"  # Legacy direct ordering remains supported.
    assert _load(CANONICAL)["status"] == "active"


def test_cpu_inference_alias_preserves_its_exact_certified_provenance():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    metadata = catalog["metadata"]

    assert metadata["showroom_content_repo_url"] == "https://github.com/jkershawrh/launchpad.git"
    assert metadata["showroom_content_ref"] == CONTENT_REVISION
    assert metadata["source_content_repo"] == "https://github.com/jkershawrh/launchpad.git"
    assert metadata["source_content_revision"] == CONTENT_REVISION
    assert intake["sources"]["showroom"]["revision"] == CONTENT_REVISION
    assert metadata["workload_repo"] == "https://github.com/rh-ai-quickstart/llm-cpu-serving.git"
    assert metadata["workload_revision"] == WORKLOAD_REVISION
    assert intake["sources"]["workload"]["revision"] == WORKLOAD_REVISION
    assert metadata["hardware_claim_status"] == "platform-declared"

    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["catalog_item_id"] == "cpu-inference-serving"
    assert evidence["result"] == "GREEN-live"
    assert evidence["contract"]["catalog_version"] == catalog["version"]
    assert evidence["order"]["seat_count"] == 5
    assert evidence["cleanup"]["model_keys_revoked"] is True
    assert all(count == 0 for count in evidence["cleanup"]["resource_counts"].values())


def test_cpu_inference_alias_uses_the_certified_story_terminal_workspace_console_surfaces():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    expected_tabs = [
        {"id": "terminal", "title": "Terminal", "source": "showroom.terminal"},
        {"id": "workspace", "title": "RAG Assistant", "source": "workload.route.ui"},
        {
            "id": "openshift-console",
            "title": "OpenShift Console",
            "source": "cluster.console_url",
        },
    ]

    assert catalog["metadata"]["showroom_tabs"] == expected_tabs
    assert intake["runtime"]["tabs"] == expected_tabs
    assert catalog["metadata"]["showroom_journey"] == "intel-llm-cpu-serving"
    assert catalog["metadata"]["content_only"] is True


def test_cpu_inference_alias_retains_its_exact_five_seat_certification_contract():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    contract = _load(CERTIFICATION)

    assert catalog["metadata"]["certification_stage"] == "5-seat-certified"
    assert intake["certification"]["certified_seats"] == 5
    assert intake["certification"]["max_workshop_seats"] == 5
    assert intake["certification"]["activation_blockers"] == []
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1, 5]
