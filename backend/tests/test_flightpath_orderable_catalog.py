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
        "cpu-inference-serving",
        "intel-llm-cpu-serving",
        "network-operations-agent",
        "rag-on-xeon",
        "virtualization-ai-401",
    }


def test_specialty_catalog_status_matches_certification_evidence():
    items = _catalog_items()
    expected = {
        "ai-sandbox": "draft",
        "cpu-inference-serving": "active",
        "intel-llm-tool-calling": "draft",
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
        "6d7c6f267407d42ca465b8a381d841d8b5b77567"
    )
    assert metadata["workload_revision"] == metadata["showroom_content_ref"]
    assert metadata["workload_helm_values"]["workload_image"].endswith(
        "@sha256:c7f5058213960ceb1a268506f43fe666c4cf5df62ce7d6e444dd277b34886958"
    )
    assert metadata["workload_helm_values"]["presentation_image"].endswith(
        "@sha256:c9301b53eca8b8a20c9f87d142363b7c9b0f2abffeb36fd6b97ee3ebb895ec2d"
    )
    assert metadata["activation_blockers"]


def test_agentic_501_is_mounted_as_a_fail_closed_destination_qualification_draft():
    item = _effective_flightpath_items()["scale-agentic-blueprint"]
    metadata = item["metadata"]

    assert item["status"] == "draft"
    assert metadata["certification_stage"] == "immutable-source-published"
    assert metadata["max_workshop_seats"] == 1
    assert metadata["allowed_exposure_policies"] == ["internal"]
    assert metadata["workload_revision"] == "ae23851fb5d24523930abc6a4639205f072e93a7"
    assert metadata["showroom_content_ref"] == metadata["workload_revision"]
    assert metadata["workload_helm_values"]["images"] == {
        "presentation": {
            "repository": "ghcr.io/jkershawrh/agentic-scale-501-presentation",
            "digest": "sha256:ac1e22061238bda32fb41338c4fe03f2a3bf801fffbcd0bc3350a87f93f9fc21",
        },
        "qualifier": {
            "repository": "ghcr.io/jkershawrh/agentic-scale-501-qualifier",
            "digest": "sha256:24b265cc26b4c6e6a84a2adf3cb463613c883d92e33e7937ae0487a3cbab6330",
        },
    }
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
    assert metadata["certification_stage"] == "immutable-source-published"
    assert metadata["max_workshop_seats"] == 1
    assert metadata["prerequisites"] == [
        "operate-agentic-blueprint",
        "scale-agentic-blueprint",
    ]
    assert metadata["allowed_exposure_policies"] == ["internal"]
    assert metadata["workload_revision"] == "22f4e4656843721c66b0779e52c30fc46a4061de"
    assert metadata["showroom_content_ref"] == metadata["workload_revision"]
    assert metadata["workload_helm_values"]["images"] == {
        "presentation": {
            "repository": "ghcr.io/jkershawrh/agentic-ai-601-presentation",
            "digest": "sha256:4442f16d4d401c376a86dbcfa0acc111abf78c8cd0668f149adb41a6dc35192e",
        },
        "qualifier": {
            "repository": "ghcr.io/jkershawrh/agentic-ai-601-qualifier",
            "digest": "sha256:5a80d8c2a5f3031c2c90e3b0059123633a2984d54344ab6e964a21b9b537fafc",
        },
    }
    assert metadata["workload_helm_values"]["routes"] == {
        "enabled": True,
        "ingressDomain": "apps.flightpath.fm2aihpcsed.com",
    }
    assert metadata["workload_helm_values"]["qualifier"] == {
        "sourceState": "rehearsal",
        "authorityExecutionEnabled": False,
    }
    assert metadata["activation_blockers"]
