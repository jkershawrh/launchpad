from __future__ import annotations

from copy import deepcopy

import pytest
from app.domain.catalog_intake import CatalogIntakeSubmission
from app.services.catalog_intake_submissions import CatalogIntakeSubmissionService
from pydantic import ValidationError


def _submission(**updates) -> CatalogIntakeSubmission:
    payload = {
        "catalog_item_id": "example-agent-lab",
        "display_name": "Example Agent Lab",
        "repository_url": "https://github.com/example/agent-lab.git",
        "revision": "a" * 40,
        "owner": "solution-owner@example.com",
        "audience": ["intel-sellers", "solution-architects"],
        "duration_hours": 4,
        "lab_type": "guided_build",
        "expected_scale": 25,
    }
    payload.update(updates)
    return CatalogIntakeSubmission(**payload)


def test_draft_submission_is_deterministic_safe_and_non_orderable():
    service = CatalogIntakeSubmissionService()

    first = service.submit(_submission())
    second = service.submit(_submission())

    assert first == second
    assert first.intake_id.startswith("intake-")
    assert first.state == "draft"
    assert first.orderable is False
    assert first.promotion_eligible is False
    assert first.defaults.exposure_policies == ["internal"]
    assert first.defaults.maximum_seats == 1
    assert first.requested.expected_scale == 25
    assert first.supported_targets == []
    assert first.target_status == "unverified"
    assert first.evidence.status == "not-run"
    assert first.evidence.artifacts == []
    assert first.approval_history == []
    assert first.rollback.status == "not-defined"
    assert first.release_identity.repository_url == (
        "https://github.com/example/agent-lab.git"
    )
    assert first.release_identity.revision == "a" * 40
    assert any("25-seat" in blocker for blocker in first.blockers)
    assert any("Durable intake persistence" in blocker for blocker in first.blockers)
    assert service.list_all() == [first]
    assert service.get(first.intake_id) == first


def test_draft_submission_normalizes_audience_without_mutating_input():
    submission = _submission(
        audience=[" solution-architects ", "intel-sellers", "intel-sellers"]
    )
    original = deepcopy(submission)

    draft = CatalogIntakeSubmissionService().submit(submission)

    assert draft.requested.audience == ["intel-sellers", "solution-architects"]
    assert submission == original


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"repository_url": "http://github.com/example/repo"}, "HTTPS GitHub"),
        ({"repository_url": "https://example.com/example/repo"}, "HTTPS GitHub"),
        ({"revision": "main"}, "immutable 40-character Git SHA"),
        ({"catalog_item_id": "Unsafe ID"}, "DNS-safe"),
        ({"owner": " "}, "owner"),
        ({"audience": []}, "audience"),
        ({"duration_hours": 0}, "greater than or equal to 1"),
        ({"expected_scale": 0}, "greater than or equal to 1"),
        ({"lab_type": "production"}, "quick_start"),
    ],
)
def test_submission_contract_rejects_unsafe_or_incomplete_requests(updates, message):
    with pytest.raises(ValidationError, match=message):
        _submission(**updates)


def test_submission_contract_forbids_attempted_promotion_fields():
    payload = _submission().model_dump()
    payload.update(
        {
            "status": "active",
            "exposure_policy": "public_code",
            "supported_targets": ["arena"],
        }
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CatalogIntakeSubmission(**payload)


def test_service_returns_copies_and_missing_intake_is_not_found():
    service = CatalogIntakeSubmissionService()
    created = service.submit(_submission(expected_scale=1))
    returned = service.get(created.intake_id)
    assert returned is not None
    returned.blockers.append("tampered")

    assert "tampered" not in service.get(created.intake_id).blockers
    assert service.get("intake-missing") is None
