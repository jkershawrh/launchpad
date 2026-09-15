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


def _catalog_item(catalog_item_id: str) -> dict:
    path = REPO_ROOT / "catalog" / catalog_item_id / "catalog-item.yaml"
    return yaml.safe_load(path.read_text())


def test_thirty_seat_is_next_candidate_without_bypassing_public_certification():
    platform_config = yaml.safe_load(
        (REPO_ROOT / "deploy/launchpad/base/configmap.yaml").read_text()
    )
    assert int(platform_config["data"]["MAX_ACTIVE_SESSIONS_PER_WORKSHOP"]) >= 30

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
    assert intake["certification"]["max_workshop_seats"] == 25
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
    assert plan["certification_override"] is True
    assert plan["execution_eligible"] is True
    assert plan["required_consecutive_runs"] == 3
