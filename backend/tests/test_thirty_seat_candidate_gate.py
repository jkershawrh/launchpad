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
    "intel-llm-cpu-serving": "flightpath",
    "intel-xeon6-agent-201": "flightpath",
    "multi-agent-quickstart": "flightpath",
}
CURRENT_LIMITS = {
    "intel-llm-cpu-serving": ("active", "five-seat-certified", 5),
    "intel-xeon6-agent-201": (
        "draft",
        "source-candidate-recertification-required",
        1,
    ),
    "multi-agent-quickstart": ("draft", "immutable-source-published", 1),
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


def test_historical_thirty_seat_runs_do_not_promote_a_new_flightpath_candidate():
    platform_config = yaml.safe_load(
        (REPO_ROOT / "deploy/launchpad/base/configmap.yaml").read_text()
    )
    assert int(platform_config["data"]["MAX_ACTIVE_SESSIONS_PER_WORKSHOP"]) >= 30

    for catalog_item_id in CATALOG_ITEMS:
        catalog = _catalog_item(catalog_item_id)
        metadata = catalog["metadata"]

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

        # Those runs belong to earlier artifacts and targets. The current
        # Flightpath candidate stays at its independently certified limit.
        status, stage, max_seats = CURRENT_LIMITS[catalog_item_id]
        assert catalog["status"] == status
        assert metadata["certification_stage"] == stage
        assert metadata["max_workshop_seats"] == max_seats
        assert max_seats < 30
        assert metadata["workshop_cluster_ref"] == EVENT_CLUSTERS[catalog_item_id]


@pytest.mark.parametrize(
    ("catalog_item_id", "expected_profiles", "intake_status"),
    (
        ("intel-llm-cpu-serving", [1, 5], "pass"),
        ("intel-xeon6-agent-201", [1, 5, 25, 30], "fail"),
        ("multi-agent-quickstart", [1, 5, 25, 30], "pass"),
    ),
)
def test_current_flightpath_contract_stays_at_its_truthful_certified_limit(
    catalog_item_id: str,
    expected_profiles: list[int],
    intake_status: str,
):
    catalog = _catalog_item(catalog_item_id)
    metadata = catalog["metadata"]
    intake_path = REPO_ROOT / metadata["onboarding_contract"]
    contract_path = REPO_ROOT / metadata["certification_proof_contract"]

    intake = load_intake(intake_path)
    contract = load_certification_contract(contract_path)

    intake_validation = validate_intake(intake)
    assert intake_validation["validation_status"] == intake_status
    if intake_status == "fail":
        assert intake_validation["activation_status"] == "blocked"
        assert intake_validation["errors"] == [
            "sources.workload.revision must be an immutable 40-character Git SHA"
        ]
    assert validate_certification_contract(
        contract,
        intake=intake,
        repo_root=REPO_ROOT,
        contract_path=contract_path,
    ) == []
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == (
        expected_profiles
    )
    status, stage, max_seats = CURRENT_LIMITS[catalog_item_id]
    assert catalog["status"] == status
    assert intake["certification"]["stage"] == stage
    assert intake["certification"]["max_workshop_seats"] == max_seats
    assert intake["certification"]["proof_contract"] == str(
        contract_path.relative_to(REPO_ROOT)
    )
    assert catalog["metadata"]["certification_proof_contract"] == str(
        contract_path.relative_to(REPO_ROOT)
    )

    plan = build_certification_plan(
        contract,
        intake=intake,
        seats=max_seats,
        exposure_policy="internal",
    )
    assert plan["cluster_ref"] == "flightpath"
    assert plan["execution_eligible"] is True
    assert plan["seats"] == max_seats
    assert plan["required_consecutive_runs"] == 1
    assert plan["current_certified_seats"] <= max_seats


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
