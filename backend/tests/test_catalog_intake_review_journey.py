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
from app.services.catalog_intake_discovery_coordinator import (
    CatalogIntakeDiscoveryCoordinator,
    DisabledCatalogIntakeDiscoveryDispatcher,
)
from app.services.catalog_intake_pipeline import build_catalog_intake_pipeline_view
from app.services.catalog_intake_submissions import CatalogIntakeSubmissionService
from app.services.catalog_onboarding import discover_quickstart_repo
from app.storage.catalog_intakes import (
    CatalogIntakeDraftConflictError,
    InMemoryCatalogIntakeDraftStore,
)

REPOSITORY = "https://github.com/example/quickstart.git"
REVISION = "a" * 40


class _DurableMemoryStore(InMemoryCatalogIntakeDraftStore):
    durable = True


class _FakeDispatcher:
    available = True
    worker_image_digest = "sha256:" + "b" * 64

    def __init__(self) -> None:
        self.dispatched = []

    def dispatch(self, request, approval) -> None:
        self.dispatched.append((request, approval))


class _FailingDispatcher(_FakeDispatcher):
    def dispatch(self, request, approval) -> None:
        raise RuntimeError("credential-like-sensitive-dispatch-detail")


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
        "approve_source": False,
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


def test_approved_intake_dispatches_and_collects_a_reviewable_result(
    tmp_path: Path,
) -> None:
    service = CatalogIntakeSubmissionService(store=_DurableMemoryStore())
    dispatcher = _FakeDispatcher()
    coordinator = CatalogIntakeDiscoveryCoordinator(service, dispatcher)
    submitted = service.submit(_submission())

    before = build_catalog_intake_pipeline_view(
        submitted, isolated_worker_available=True
    )
    assert before.actions.approve_source is True
    assert before.actions.run_discovery is False

    approved = service.approve_source(
        submitted.intake_id, approved_by="catalog-reviewer"
    )
    ready = build_catalog_intake_pipeline_view(
        approved, isolated_worker_available=True
    )
    assert ready.actions.approve_source is False
    assert ready.actions.run_discovery is True

    running = coordinator.start(submitted.intake_id, requested_by="catalog-reviewer")
    assert running.discovery_execution is not None
    assert running.discovery_execution.state == "running"
    assert len(dispatcher.dispatched) == 1
    request, approval = dispatcher.dispatched[0]
    assert request.source_approval_id == approval.approval_id

    receipt = _receipt(tmp_path, submitted.intake_id)
    receipt = receipt.model_copy(
        update={
            "attempt_id": request.attempt_id,
            "cleanup": receipt.cleanup.model_copy(
                update={"attempt_id": request.attempt_id}
            ),
        }
    )
    completed = coordinator.collect(receipt)
    assert completed.discovery_execution is None
    assert completed.catalog_preview is not None


def test_disabled_dispatcher_fails_before_queueing_work() -> None:
    service = CatalogIntakeSubmissionService(store=_DurableMemoryStore())
    submitted = service.submit(_submission())
    service.approve_source(submitted.intake_id, approved_by="catalog-reviewer")
    coordinator = CatalogIntakeDiscoveryCoordinator(
        service, DisabledCatalogIntakeDiscoveryDispatcher()
    )

    with pytest.raises(ValueError, match="not available"):
        coordinator.start(submitted.intake_id, requested_by="catalog-reviewer")

    unchanged = service.get(submitted.intake_id)
    assert unchanged is not None
    assert unchanged.discovery_execution is None


def test_dispatch_failure_is_sanitized_and_persisted() -> None:
    service = CatalogIntakeSubmissionService(store=_DurableMemoryStore())
    submitted = service.submit(_submission())
    service.approve_source(submitted.intake_id, approved_by="catalog-reviewer")
    coordinator = CatalogIntakeDiscoveryCoordinator(service, _FailingDispatcher())

    with pytest.raises(ValueError, match="discovery dispatch failed") as failure:
        coordinator.start(submitted.intake_id, requested_by="catalog-reviewer")

    assert "sensitive" not in str(failure.value)
    failed = service.get(submitted.intake_id)
    assert failed is not None and failed.discovery_execution is not None
    assert failed.discovery_execution.state == "failed"
    assert failed.discovery_execution.error_codes == ["dispatch-failed"]


def test_collector_rejects_a_receipt_for_another_attempt() -> None:
    service = CatalogIntakeSubmissionService(store=_DurableMemoryStore())
    dispatcher = _FakeDispatcher()
    coordinator = CatalogIntakeDiscoveryCoordinator(service, dispatcher)
    submitted = service.submit(_submission())
    service.approve_source(submitted.intake_id, approved_by="catalog-reviewer")
    coordinator.start(submitted.intake_id, requested_by="catalog-reviewer")
    now = datetime.now(UTC)
    wrong = CatalogIntakeDiscoveryReceipt(
        intake_id=submitted.intake_id,
        attempt_id="attempt-wrong",
        idempotency_key="sha256:" + "c" * 64,
        repository_url=REPOSITORY,
        revision=REVISION,
        policy_version="1.0.0",
        source_approval_id="approval-wrong",
        worker_image_digest="sha256:" + "b" * 64,
        started_at=now,
        finished_at=now,
        status="failed",
        error_codes=["worker-failed"],
        scan_summary={"files_scanned": 0, "bytes_scanned": 0},
        cleanup=CatalogIntakeCleanupReceipt(
            receipt_id="sha256:" + "d" * 64,
            attempt_id="attempt-wrong",
            workspace_removed=True,
            result="pass",
        ),
    )

    with pytest.raises(ValueError, match="attempt identity"):
        coordinator.collect(wrong)


def test_discovery_bridge_contract_keeps_live_authority_disabled() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = yaml.safe_load(
        (root / "contracts/catalog-intake-discovery-bridge-v1.yaml").read_text()
    )

    assert contract["dispatch"]["default_runtime"] == "disabled"
    assert contract["collection"]["matching_attempt_required"] is True
    assert contract["admin_actions"]["run_discovery"] == "conditional"
    assert all(value is False for value in contract["authority"].values())
