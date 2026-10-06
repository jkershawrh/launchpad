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


def test_publication_queue_records_a_self_consistent_dated_snapshot() -> None:
    queue = yaml.safe_load(QUEUE.read_text(encoding="utf-8"))

    assert queue["generated_at"].startswith("2026-09-30")
    for item in queue["queue"]:
        assert len(item["current_catalog_revision"]) == 40
        assert all(
            character in "0123456789abcdef"
            for character in item["current_catalog_revision"]
        )
        assert item["source_repository"].endswith(".git")
