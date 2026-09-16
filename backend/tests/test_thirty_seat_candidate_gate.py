import json
from pathlib import Path

import pytest
import yaml
from app.services.catalog_certification import (
    build_certification_plan,
    load_certification_contract,
    validate_certification_contract,
)
from app.services.catalog_onboarding import load_intake, validate_intake

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_ITEMS = (
    "intel-llm-cpu-serving",
    "intel-xeon6-agent-201",
    "multi-agent-quickstart",
)
EVENT_CLUSTERS = {
    "intel-llm-cpu-serving": "arena",
    "intel-xeon6-agent-201": "brutus",
    "multi-agent-quickstart": "arena",
}


def _catalog_item(catalog_item_id: str) -> dict:
    path = REPO_ROOT / "catalog" / catalog_item_id / "catalog-item.yaml"
    return yaml.safe_load(path.read_text())


def _successful_thirty_seat_runs(catalog_item_id: str) -> list[dict]:
    runs = []
    for path in sorted(
        (REPO_ROOT / "evidence/runs").glob(f"{catalog_item_id}-30-seat-*.json")
    ):
        evidence = json.loads(path.read_text())
        if evidence["result"] == "GREEN-live":
            runs.append(evidence)
    return runs


def test_thirty_seat_is_promoted_only_after_three_repeatable_green_live_runs():
    platform_config = yaml.safe_load(
        (REPO_ROOT / "deploy/launchpad/base/configmap.yaml").read_text()
    )
    assert int(platform_config["data"]["MAX_ACTIVE_SESSIONS_PER_WORKSHOP"]) >= 30

    for catalog_item_id in CATALOG_ITEMS:
        metadata = _catalog_item(catalog_item_id)["metadata"]

        runs = _successful_thirty_seat_runs(catalog_item_id)
        assert len(runs) >= 3
        for evidence in runs[-3:]:
            assert evidence["rubric"] == {
                **evidence["rubric"],
                "passed": True,
                "score": 100,
            }
            assert evidence["cleanup"]["status"] == "completed"
            assert evidence["cleanup"]["model_keys_revoked"] is True
            assert set(evidence["cleanup"]["resource_counts"].values()) == {0}

        # The public/catalog limit can advance only after the repeatability
        # evidence above has passed. This keeps source promotion fail-closed.
        assert metadata["certification_stage"] == "thirty-seat-certified"
        assert metadata["max_workshop_seats"] == 30
        assert metadata["promotion_sequence"][-1] == 30
        assert metadata["workshop_cluster_ref"] == EVENT_CLUSTERS[catalog_item_id]


@pytest.mark.parametrize(
    ("catalog_item_id", "cluster_ref"),
    (
        ("intel-llm-cpu-serving", "arena"),
        ("intel-xeon6-agent-201", "brutus"),
        ("multi-agent-quickstart", "arena"),
    ),
)
def test_every_thirty_seat_candidate_has_a_valid_repeatable_proof_contract(
    catalog_item_id: str,
    cluster_ref: str,
):
    catalog = _catalog_item(catalog_item_id)
    intake_path = REPO_ROOT / "catalog-onboarding" / f"{catalog_item_id}.yaml"
    contract_path = REPO_ROOT / "certification/catalog" / f"{catalog_item_id}.yaml"

    intake = load_intake(intake_path)
    contract = load_certification_contract(contract_path)

    assert validate_intake(intake)["validation_status"] == "pass"
    assert validate_certification_contract(
        contract,
        intake=intake,
        repo_root=REPO_ROOT,
        contract_path=contract_path,
    ) == []
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [
        1,
        5,
        25,
        30,
    ]
    assert intake["certification"]["stage"] == "thirty-seat-certified"
    assert intake["certification"]["max_workshop_seats"] == 30
    assert intake["certification"]["proof_contract"] == str(
        contract_path.relative_to(REPO_ROOT)
    )
    assert catalog["metadata"]["certification_proof_contract"] == str(
        contract_path.relative_to(REPO_ROOT)
    )

    plan = build_certification_plan(
        contract,
        intake=intake,
        seats=30,
        exposure_policy="internal",
    )
    assert plan["cluster_ref"] == cluster_ref
    assert plan["certification_override"] is False
    assert plan["execution_eligible"] is True
    assert plan["required_consecutive_runs"] == 3
    assert plan["current_certified_seats"] == 30
    assert plan["next_promotion_target"] is None


def test_multi_agent_contract_matches_current_showroom_and_probe_interface():
    contract = load_certification_contract(
        REPO_ROOT / "certification/catalog/multi-agent-quickstart.yaml"
    )

    markers = {
        page["id"]: page["marker"]
        for page in contract["spec"]["showroom"]["pages"]
    }
    assert markers["track-chooser"] == "One Lab, One Guided Journey"
    assert markers["track-1-local"] == "Track 1: Understand the Application Pattern"
    assert contract["spec"]["seat_probe"]["argv"][-2:] == [
        "{namespace}",
        "{cluster_ref}",
    ]
