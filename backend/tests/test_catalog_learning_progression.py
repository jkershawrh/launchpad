from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog"
CONTRACT = ROOT / "contracts" / "catalog-learning-progression-v1.yaml"
FLIGHTPATH_CANDIDATES = (
    ROOT / "deploy" / "launchpad" / "overlays" / "flightpath-candidate"
)


def _items() -> dict[str, dict]:
    items = {}
    for path in sorted(CATALOG.glob("*/catalog-item.yaml")):
        document = yaml.safe_load(path.read_text())
        items[document["catalog_item_id"]] = document
    return items


def test_catalog_learning_metadata_matches_versioned_contract():
    contract = yaml.safe_load(CONTRACT.read_text())
    items = _items()
    levels = contract["levels"]

    for catalog_id, item in items.items():
        metadata = item["metadata"]
        for field in contract["required_metadata"]:
            assert field in metadata, f"{catalog_id} is missing {field}"
        level = str(metadata["learning_level"]).zfill(3)
        assert level in levels
        assert metadata["learning_stage"] == levels[level]["name"]
        assert isinstance(metadata["prerequisites"], list)
        assert isinstance(metadata["recommended_next_items"], list)
        assert catalog_id not in metadata["prerequisites"]
        assert catalog_id not in metadata["recommended_next_items"]
        for reference in metadata["prerequisites"] + metadata["recommended_next_items"]:
            assert reference in items, f"{catalog_id} references unknown item {reference}"


def test_public_learning_titles_include_their_level():
    for catalog_id, item in _items().items():
        metadata = item["metadata"]
        if metadata["experience_type"] == "platform_validation":
            continue
        assert str(metadata["learning_level"]).zfill(3) in item["display_name"], catalog_id


def test_internal_platform_validation_title_is_explicit():
    smoke_test = _items()["smoke-test"]
    assert smoke_test["display_name"] == "Launchpad 001: Platform Smoke Test"


def test_catalog_ids_and_runtime_versions_remain_independent_of_learning_level():
    contract = yaml.safe_load(CONTRACT.read_text())
    assert contract["compatibility"]["catalog_ids_are_stable"] is True
    assert contract["compatibility"]["runtime_release_versions_unchanged_by_taxonomy"] is True
    for catalog_id, item in _items().items():
        assert item["catalog_item_id"] == catalog_id
        assert item["version"]


def test_flightpath_candidate_titles_match_canonical_learning_titles():
    canonical = _items()
    for path in sorted(FLIGHTPATH_CANDIDATES.glob("*.catalog-item.yaml")):
        candidate = yaml.safe_load(path.read_text())
        catalog_id = candidate["catalog_item_id"]
        assert catalog_id in canonical
        assert candidate["display_name"] == canonical[catalog_id]["display_name"]
