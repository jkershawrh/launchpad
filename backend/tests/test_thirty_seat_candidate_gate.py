from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_ITEMS = (
    "intel-llm-cpu-serving",
    "intel-xeon6-agent-201",
    "multi-agent-quickstart",
)


def _catalog_item(catalog_item_id: str) -> dict:
    path = REPO_ROOT / "catalog" / catalog_item_id / "catalog-item.yaml"
    return yaml.safe_load(path.read_text())


def test_thirty_seat_is_next_candidate_without_bypassing_public_certification():
    for catalog_item_id in CATALOG_ITEMS:
        metadata = _catalog_item(catalog_item_id)["metadata"]

        # Public orders remain fail-closed at the last proven scale. The
        # internal certification runner may exercise only the declared next
        # target before a separate promotion changes this limit.
        assert metadata["max_workshop_seats"] == 25
        larger_targets = sorted(
            target
            for target in metadata["promotion_sequence"]
            if target > metadata["max_workshop_seats"]
        )
        assert larger_targets == [30]
