from pathlib import Path

import pytest
import yaml

from app.services.catalog_onboarding import load_intake, validate_intake

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog"
CONTRACT = ROOT / "contracts" / "catalog-learning-progression-v1.yaml"
BLUEPRINT_CONTRACT = ROOT / "contracts" / "agentic-blueprint-v1.yaml"
TELEMETRY_CONTRACT = ROOT / "contracts" / "agentic-journey-telemetry-v1.yaml"
FLIGHTPATH_CANDIDATES = (
    ROOT / "deploy" / "launchpad" / "overlays" / "flightpath-candidate"
)
ONBOARDING = ROOT / "catalog-onboarding"


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


def test_catalog_journey_roles_form_valid_core_and_specialty_paths():
    contract = yaml.safe_load(CONTRACT.read_text())
    items = _items()
    roles = set(contract["journey_roles"])
    specialty_families = set(contract["specialty_families"])
    solution_families = set(contract["solution_families"])
    canonical_blueprints = contract["canonical_blueprints"]

    for catalog_id, item in items.items():
        metadata = item["metadata"]
        assert metadata["journey_role"] in roles
        assert metadata["specialty_family"] in specialty_families | {None}
        assert metadata["solution_family"] in solution_families
        assert metadata["shared_blueprint"] in set(canonical_blueprints.values()) | {None}
        for field in ("branches_from", "returns_to"):
            reference = metadata[field]
            assert reference is None or reference in items, (
                f"{catalog_id} {field} references unknown item {reference}"
            )

        if metadata["journey_role"] == "core":
            expected_blueprint = canonical_blueprints.get(
                metadata["solution_family"], contract["canonical_blueprint"]
            )
            assert metadata["shared_blueprint"] == expected_blueprint
            assert metadata["specialty_family"] is None
        elif metadata["journey_role"] == "specialty":
            assert metadata["specialty_family"] is not None
            assert metadata["branches_from"] is not None


def test_agentic_blueprint_and_telemetry_contracts_share_identity():
    progression = yaml.safe_load(CONTRACT.read_text())
    blueprint = yaml.safe_load(BLUEPRINT_CONTRACT.read_text())
    telemetry = yaml.safe_load(TELEMETRY_CONTRACT.read_text())

    assert blueprint["blueprint_id"] == progression["canonical_blueprint"]
    assert telemetry["blueprint_id"] == blueprint["blueprint_id"]
    assert telemetry["correlation"]["required_fields"]
    assert telemetry["journey_events"]
    assert telemetry["proof_requirements"]


def test_progression_reserves_501_for_scale_and_certification():
    contract = yaml.safe_load(CONTRACT.read_text())
    assert contract["levels"]["501"]["name"] == "Scale"
    assert contract["levels"]["501"]["publication_gate"] == "certified"


def test_progression_models_named_tracks_without_making_plans_orderable():
    contract = yaml.safe_load(CONTRACT.read_text())

    assert contract["levels"]["601"]["name"] == "Qualify"
    assert set(contract["learning_tracks"]) == {
        "agentic_ai",
        "sovereign_ai",
        "virtualization_ai",
    }
    assert (
        contract["learning_tracks"]["agentic_ai"]["entries"]["601"]["title"]
        == "Earn the Right to Act"
    )
    assert contract["track_rules"]["planned_entries_are_orderable"] is False
    assert contract["track_rules"]["draft_entries_are_orderable"] is False
    assert contract["track_rules"]["active_entries_require_current_certification"] is True
    assert contract["track_rules"]["sales_enablement_is_a_separate_persona_axis"] is True


def test_scale_blueprint_extends_401_as_a_separate_gated_catalog_item():
    items = _items()
    operate = items["operate-agentic-blueprint"]
    scale = items["scale-agentic-blueprint"]

    assert scale["status"] == "draft"
    assert scale["metadata"]["learning_level"] == "501"
    assert scale["metadata"]["prerequisites"] == ["operate-agentic-blueprint"]
    assert scale["metadata"]["shared_blueprint"] == operate["metadata"]["shared_blueprint"]
    assert scale["metadata"]["solution_family"] == "operations_reliability"
    assert scale["metadata"]["publication_gate"] == "certified"
    assert scale["metadata"]["activation_blockers"]


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


def test_new_agentic_expansion_stops_at_one_seat_for_initial_activation():
    for catalog_id in ("scale-agentic-blueprint", "agentic-ai-601"):
        item = _items()[catalog_id]
        intake = yaml.safe_load((ONBOARDING / f"{catalog_id}.yaml").read_text())

        assert item["status"] == "draft"
        assert item["metadata"]["max_workshop_seats"] == 1
        assert intake["certification"]["max_workshop_seats"] == 1
        blockers = " ".join(intake["certification"]["activation_blockers"])
        assert "one-seat" in blockers
        assert "scale certification is deferred" in blockers


@pytest.mark.parametrize(
    ("solution_family", "blueprint"),
    [
        ("agentic_ai", "red-hat-intel-agentic-v1"),
        ("sovereign_ai", "red-hat-intel-sovereign-ai-v1"),
        ("virtualization_ai", "red-hat-intel-virtualization-ai-v1"),
    ],
)
def test_core_learning_accepts_its_solution_family_blueprint(
    solution_family, blueprint
):
    intake = load_intake(ONBOARDING / "agentic-ai-601.yaml")
    intake["learning"].update(
        {
            "solution_family": solution_family,
            "shared_blueprint": blueprint,
            "journey_role": "core",
            "specialty_family": None,
        }
    )

    errors = validate_intake(intake)["errors"]

    assert not [error for error in errors if "blueprint" in error]


def test_core_learning_rejects_a_different_solution_family_blueprint():
    intake = load_intake(ONBOARDING / "agentic-ai-601.yaml")
    intake["learning"].update(
        {
            "solution_family": "sovereign_ai",
            "shared_blueprint": "red-hat-intel-agentic-v1",
            "journey_role": "core",
            "specialty_family": None,
        }
    )

    assert any(
        "canonical solution-family blueprint" in error
        for error in validate_intake(intake)["errors"]
    )
