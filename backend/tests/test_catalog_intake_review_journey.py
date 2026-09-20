from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from app.domain.catalog_intake import CatalogIntakeSubmission
from app.domain.catalog_intake_discovery import (
    CatalogIntakeCleanupReceipt,
    CatalogIntakeDiscoveryReceipt,
)
from app.services.catalog_intake_pipeline import build_catalog_intake_pipeline_view
from app.services.catalog_intake_submissions import CatalogIntakeSubmissionService
from app.services.catalog_onboarding import discover_quickstart_repo
from app.storage.catalog_intakes import CatalogIntakeDraftConflictError

REPOSITORY = "https://github.com/example/quickstart.git"
REVISION = "a" * 40


def _source(root: Path) -> Path:
    source = root / "quickstart"
    pages = source / "showroom/modules/ROOT/pages"
    pages.mkdir(parents=True)
    (source / "site.yml").write_text(
        "content:\n  sources:\n    - url: .\n      start_path: showroom\n",
        encoding="utf-8",
    )
    (source / "showroom/antora.yml").write_text(
        "name: example\ntitle: Example\nversion: ~\n",
        encoding="utf-8",
    )
    (pages / "index.adoc").write_text("= Start\n", encoding="utf-8")
    chart = source / "deploy/chart"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: example\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    (chart / "values.yaml").write_text("{}\n", encoding="utf-8")
    return source


def _submission() -> CatalogIntakeSubmission:
    return CatalogIntakeSubmission(
        catalog_item_id="example-quickstart",
        display_name="Example Quickstart",
        repository_url=REPOSITORY,
        revision=REVISION,
        owner="solution-owner",
        audience=["solution architects"],
        duration_hours=4,
        lab_type="guided_build",
        expected_scale=25,
    )


def _receipt(root: Path, intake_id: str) -> CatalogIntakeDiscoveryReceipt:
    draft_intake, report = discover_quickstart_repo(
        _source(root),
        repo_url=REPOSITORY,
        revision=REVISION,
        catalog_id="example-quickstart",
        display_name="Example Quickstart",
    )
    assert report["discovery_status"] == "pass"
    encoded = json.dumps(
        draft_intake, sort_keys=True, separators=(",", ":")
    ).encode()
    now = datetime.now(UTC)
    return CatalogIntakeDiscoveryReceipt(
        intake_id=intake_id,
        attempt_id="attempt-001",
        idempotency_key="sha256:" + "c" * 64,
        repository_url=REPOSITORY,
        revision=REVISION,
        policy_version="1.0.0",
        source_approval_id="approval-001",
        worker_image_digest="sha256:" + "b" * 64,
        started_at=now,
        finished_at=now,
        status="passed",
        scan_summary={"files_scanned": 5, "bytes_scanned": 256},
        output_hash="sha256:" + hashlib.sha256(encoded).hexdigest(),
        draft_intake=draft_intake,
        cleanup=CatalogIntakeCleanupReceipt(
            receipt_id="sha256:" + "d" * 64,
            attempt_id="attempt-001",
            workspace_removed=True,
            bytes_removed=256,
            result="pass",
        ),
    )


def test_successful_discovery_becomes_a_persisted_reviewable_catalog_draft(
    tmp_path: Path,
) -> None:
    service = CatalogIntakeSubmissionService()
    submitted = service.submit(_submission())
    receipt = _receipt(tmp_path, submitted.intake_id)

    reviewed = service.record_discovery(submitted.intake_id, receipt)
    persisted = service.get(submitted.intake_id)

    assert persisted == reviewed
    assert reviewed.discovery is not None
    assert reviewed.discovery.status == "passed"
    assert reviewed.discovery.output_hash == receipt.output_hash
    assert reviewed.discovery.files_scanned == 5
    assert reviewed.catalog_preview is not None
    assert reviewed.catalog_preview["catalog_item_id"] == "example-quickstart"
    assert reviewed.catalog_preview["status"] == "draft"
    assert reviewed.catalog_preview["metadata"]["allowed_exposure_policies"] == [
        "internal"
    ]
    assert reviewed.orderable is False
    assert reviewed.promotion_eligible is False
    assert reviewed.evidence.status == "partial"
    assert len(reviewed.evidence.artifacts) == 2
    assert not any("discovery" in item.lower() and "not been run" in item.lower() for item in reviewed.blockers)

    pipeline = build_catalog_intake_pipeline_view(reviewed)
    assert pipeline.current_stage == "draft-generated"
    assert pipeline.stages[0].status == "complete"
    assert pipeline.stages[1].status == "complete"
    assert pipeline.stages[2].status == "current"
    assert pipeline.gates[0].status == "passed"
    assert pipeline.gates[1].status == "passed"
    assert pipeline.actions.model_dump() == {
        "run_discovery": False,
        "generate_draft": False,
        "run_one_seat_certification": False,
        "request_review": False,
        "promote": False,
    }


def test_discovery_receipt_must_match_intake_and_remain_fail_closed(
    tmp_path: Path,
) -> None:
    service = CatalogIntakeSubmissionService()
    submitted = service.submit(_submission())
    receipt = _receipt(tmp_path, submitted.intake_id)

    with pytest.raises(ValueError, match="repository identity"):
        service.record_discovery(
            submitted.intake_id,
            receipt.model_copy(update={"revision": "f" * 40}),
        )

    with pytest.raises(ValueError, match="successful discovery"):
        service.record_discovery(
            submitted.intake_id,
            receipt.model_copy(
                update={"status": "failed", "error_codes": ["worker-execution-failed"]}
            ),
        )

    unchanged = service.get(submitted.intake_id)
    assert unchanged is not None
    assert unchanged.discovery is None
    assert unchanged.catalog_preview is None


def test_recording_the_same_discovery_receipt_is_idempotent(tmp_path: Path) -> None:
    service = CatalogIntakeSubmissionService()
    submitted = service.submit(_submission())
    receipt = _receipt(tmp_path, submitted.intake_id)

    first = service.record_discovery(submitted.intake_id, receipt)
    second = service.record_discovery(submitted.intake_id, receipt)

    assert first == second


def test_review_contract_keeps_every_live_mutation_locked() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = yaml.safe_load(
        (root / "contracts/catalog-intake-review-v1.yaml").read_text()
    )

    assert contract["transition"]["to"] == "draft-generated"
    assert contract["transition"]["persistence"] == "compare-and-swap"
    assert contract["review"]["catalog_preview_visible"] is True
    assert all(value is False for value in contract["authority"].values())
    assert contract["next_gate"]["state"] == "blocked"


def test_review_persistence_rejects_a_stale_concurrent_transition() -> None:
    service = CatalogIntakeSubmissionService()
    submitted = service.submit(_submission())
    first_update = submitted.model_copy(
        update={"blockers": [*submitted.blockers, "first transition"]}
    )
    stale_update = submitted.model_copy(
        update={"blockers": [*submitted.blockers, "stale transition"]}
    )

    service.store.replace(submitted, first_update)

    with pytest.raises(CatalogIntakeDraftConflictError, match="changed"):
        service.store.replace(submitted, stale_update)
