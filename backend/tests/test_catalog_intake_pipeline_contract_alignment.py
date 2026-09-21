"""CDD: the published schema must describe the existing fail-closed API view."""

from pathlib import Path

import yaml
from app.domain.catalog_intake import CatalogIntakeSubmission
from app.services.catalog_intake_pipeline import build_catalog_intake_pipeline_view
from app.services.catalog_intake_submissions import CatalogIntakeSubmissionService

CONTRACT = Path(__file__).resolve().parents[2] / "contracts/catalog-intake-pipeline-v1.1.yaml"


def _draft():
    return CatalogIntakeSubmissionService().submit(
        CatalogIntakeSubmission(
            catalog_item_id="sample-lab",
            display_name="Sample Lab",
            repository_url="https://github.com/example/sample-lab",
            revision="a" * 40,
            owner="solution-team",
            audience=["solution architects"],
            duration_hours=4,
            lab_type="guided_build",
            expected_scale=25,
        )
    )


def test_pipeline_contract_admits_both_existing_read_only_stages():
    schema = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"][
        "CatalogIntakePipelineView"
    ]["properties"]

    view = build_catalog_intake_pipeline_view(_draft())

    assert view.current_stage in schema["current_stage"]["enum"]
    assert set(schema["current_stage"]["enum"]) == {"submitted", "draft-generated"}
    assert schema["orderable"]["const"] is False
    assert schema["promotion_eligible"]["const"] is False


def test_pipeline_contract_separates_eligibility_from_mutation_authority():
    contract = yaml.safe_load(CONTRACT.read_text())
    actions = contract["components"]["schemas"]["PipelineActionSet"]["properties"]

    assert actions["approve_source"]["type"] == "boolean"
    assert actions["run_discovery"]["type"] == "boolean"
    for action in ("generate_draft", "run_one_seat_certification", "request_review", "promote"):
        assert actions[action]["const"] is False
    assert contract["x-launchpad-authority"]["response_is_authorization"] is False
    assert contract["x-launchpad-authority"]["may_mutate_live_catalog"] is False
