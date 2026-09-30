from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _catalog_items() -> dict[str, dict]:
    return {
        item["catalog_item_id"]: item
        for path in (ROOT / "catalog").glob("*/catalog-item.yaml")
        if (item := yaml.safe_load(path.read_text()))
    }


def _effective_flightpath_items() -> dict[str, dict]:
    rendered = subprocess.run(
        ["oc", "kustomize", "deploy/launchpad/overlays/flightpath-candidate"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    effective: dict[str, dict] = {}
    for document in yaml.safe_load_all(rendered):
        if not document or document.get("kind") != "ConfigMap":
            continue
        raw = (document.get("data") or {}).get("catalog-item.yaml")
        if raw:
            item = yaml.safe_load(raw)
            effective[item["catalog_item_id"]] = item
    return effective


def test_only_evidence_backed_flightpath_labs_are_participant_orderable():
    items = _effective_flightpath_items()
    active = {catalog_id for catalog_id, item in items.items() if item["status"] == "active"}

    assert active == {
        "agent-reliability",
        "cpu-inference-serving",
        "hybrid-fraud-detection",
        "intel-llm-cpu-serving",
        "intel-llm-tool-calling",
        "intel-xeon6-agent-201",
        "multi-agent-quickstart",
        "network-operations-agent",
        "rag-on-xeon",
        "ai-sandbox",
        "sovereign-ai-201",
        "virtualization-ai-201",
        "virtualization-ai-301",
    }


def test_specialty_catalog_status_matches_certification_evidence():
    items = _catalog_items()
    expected = {
        "ai-sandbox": "active",
        "cpu-inference-serving": "active",
        "intel-llm-tool-calling": "active",
        "openshift-operators-workshop": "draft",
        "rag-on-xeon": "active",
        "smoke-test": "draft",
    }

    assert {catalog_id: items[catalog_id]["status"] for catalog_id in expected} == expected


def test_rebuilt_sovereign_101_is_pinned_but_not_orderable_before_recertification():
    item = _effective_flightpath_items()["sovereign-ai-101"]
    metadata = item["metadata"]

    assert item["status"] == "draft"
    assert metadata["certification_stage"] == "immutable-source-published"
    assert metadata["showroom_content_ref"] == (
        "a23ed5c03a8ae4f68ad819bbc8ae1b6a9d62a767"
    )
    assert metadata["workload_revision"] == metadata["showroom_content_ref"]
    assert metadata["workload_helm_values"]["workload_image"].endswith(
        "@sha256:a38b17cca8ff0cea22bdd4d447503b20afd454b33f3d8a714b1ec39582420351"
    )
    assert metadata["workload_helm_values"]["presentation_image"].endswith(
        "@sha256:be49d6e3b295c784aefaa416f5ac86a02b30aca3c164baa4d4c0acd25d563e49"
    )
    assert metadata["activation_blockers"]


def test_agentic_501_is_mounted_as_a_fail_closed_destination_qualification_draft():
    item = _effective_flightpath_items()["scale-agentic-blueprint"]
    metadata = item["metadata"]

    assert item["status"] == "draft"
    assert metadata["certification_stage"] == "factory-development-verified"
    assert metadata["max_workshop_seats"] == 1
    assert metadata["allowed_exposure_policies"] == ["internal"]
    assert metadata["workload_revision"] == "5413bb24b25e67e7fba9d2025c4e4b070e324878"
    assert metadata["showroom_content_ref"] == metadata["workload_revision"]
    assert metadata["workload_helm_values"]["routes"] == {
        "enabled": True,
        "ingressDomain": "apps.flightpath.fm2aihpcsed.com",
    }
    assert metadata["workload_helm_values"]["qualifier"]["evidenceSource"] == "rehearsal"
    assert metadata["workload_helm_values"]["qualifier"]["live"]["enabled"] is False
    assert metadata["activation_blockers"]


def test_agentic_601_is_mounted_as_a_prerequisite_gated_draft():
    item = _effective_flightpath_items()["agentic-ai-601"]
    metadata = item["metadata"]

    assert item["status"] == "draft"
    assert metadata["certification_stage"] == "source-qualified"
    assert metadata["max_workshop_seats"] == 1
    assert metadata["prerequisites"] == [
        "operate-agentic-blueprint",
        "scale-agentic-blueprint",
    ]
    assert metadata["allowed_exposure_policies"] == ["internal"]
    assert metadata["workload_revision"] == "a40f01396adcccdb93c240b8c5b5b45cf418c317"
    assert metadata["showroom_content_ref"] == metadata["workload_revision"]
    assert metadata["workload_helm_values"]["routes"] == {
        "enabled": True,
        "ingressDomain": "apps.flightpath.fm2aihpcsed.com",
    }
    assert metadata["workload_helm_values"]["qualifier"] == {
        "sourceState": "rehearsal",
        "authorityExecutionEnabled": False,
    }
    assert metadata["activation_blockers"]
