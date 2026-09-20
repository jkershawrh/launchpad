from app.domain.catalog_intake import CatalogIntakeSubmission
from app.services.catalog_intake_pipeline import build_catalog_intake_pipeline_view
from app.services.catalog_intake_submissions import CatalogIntakeSubmissionService


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


def test_pipeline_is_visible_but_all_mutating_actions_fail_closed() -> None:
    view = build_catalog_intake_pipeline_view(_draft())

    assert view.source_standard == "quickstart-repository"
    assert view.metadata_policy == "discover-from-source"
    assert view.current_stage == "submitted"
    assert view.orderable is False
    assert view.promotion_eligible is False
    assert view.durable_storage is False
    assert view.isolated_worker_available is False
    assert view.stages[0].status == "current"
    assert all(stage.status == "locked" for stage in view.stages[1:])
    assert view.actions.model_dump() == {
        "run_discovery": False,
        "generate_draft": False,
        "run_one_seat_certification": False,
        "request_review": False,
        "promote": False,
    }


def test_pipeline_names_every_required_gate_and_evidence_family() -> None:
    view = build_catalog_intake_pipeline_view(_draft())

    assert [gate.gate_id for gate in view.gates] == [
        "repository-discovery",
        "catalog-draft",
        "artifact-security",
        "one-seat-lifecycle",
        "target-qualification",
        "human-approval",
        "catalog-publication",
    ]
    first = view.gates[0]
    assert first.status == "blocked"
    assert "discovery receipt" in first.required_evidence
    assert any("Durable intake persistence" in item for item in first.blockers)
    assert any("isolated intake worker" in item for item in first.blockers)


def test_worker_availability_does_not_bypass_durable_storage_or_evidence() -> None:
    view = build_catalog_intake_pipeline_view(_draft(), isolated_worker_available=True)

    assert view.isolated_worker_available is True
    assert view.actions.run_discovery is False
    assert view.gates[0].status == "blocked"
    assert any("Durable intake persistence" in item for item in view.gates[0].blockers)
