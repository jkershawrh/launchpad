from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "evidence/foundation-lab-publication-queue-20260930.yaml"


def test_foundation_publication_queue_is_immutable_and_complete() -> None:
    queue = yaml.safe_load(QUEUE.read_text(encoding="utf-8"))
    expected = {
        "ai-sandbox",
        "openshift-operators-workshop",
        "intel-llm-cpu-serving",
        "intel-llm-tool-calling",
        "intel-xeon6-agent-201",
    }

    assert {item["catalog_item_id"] for item in queue["queue"]} == expected
    assert queue["launchpad_source"]["publication_state"] == (
        "reviewed-content-published"
    )
    assert len(queue["launchpad_source"]["reviewed_content_revision"]) == 40
    assert len(queue["launchpad_source"]["published_pin_revision"]) == 40

    for item in queue["queue"]:
        assert item["source_repository"].startswith("https://github.com/")
        assert len(item["current_catalog_revision"]) == 40
        assert item["source_paths"]
        assert item["unpublished_artifacts"]
        assert item["narrow_next_action"]


def test_publication_queue_matches_current_catalog_and_onboarding_pins() -> None:
    queue = yaml.safe_load(QUEUE.read_text(encoding="utf-8"))

    for item in queue["queue"]:
        catalog_id = item["catalog_item_id"]
        catalog = yaml.safe_load(
            (ROOT / f"catalog/{catalog_id}/catalog-item.yaml").read_text(
                encoding="utf-8"
            )
        )
        onboarding = yaml.safe_load(
            (ROOT / f"catalog-onboarding/{catalog_id}.yaml").read_text(
                encoding="utf-8"
            )
        )
        metadata = catalog.get("metadata") or {}
        showroom = onboarding["sources"]["showroom"]

        if catalog_id == "ai-sandbox":
            catalog_revision = showroom["revision"]
        else:
            catalog_revision = metadata["showroom_content_ref"]

        assert item["current_catalog_revision"] == catalog_revision
        assert item["current_catalog_revision"] == showroom["revision"]
        assert item["source_repository"] == showroom["repo_url"]
