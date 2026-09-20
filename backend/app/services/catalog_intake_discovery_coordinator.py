from __future__ import annotations

from typing import Protocol

from app.domain.catalog_intake import CatalogIntakeDraft
from app.domain.catalog_intake_discovery import (
    CatalogIntakeDiscoveryReceipt,
    CatalogIntakeDiscoveryRequest,
    CatalogIntakeSourceApproval,
)
from app.services.catalog_intake_submissions import CatalogIntakeSubmissionService


class CatalogIntakeDiscoveryDispatcher(Protocol):
    available: bool
    worker_image_digest: str

    def dispatch(
        self,
        request: CatalogIntakeDiscoveryRequest,
        approval: CatalogIntakeSourceApproval,
    ) -> None: ...


class DisabledCatalogIntakeDiscoveryDispatcher:
    available = False
    worker_image_digest = "sha256:" + "0" * 64

    def dispatch(self, request, approval) -> None:
        raise RuntimeError("isolated discovery worker is not configured")


class CatalogIntakeDiscoveryCoordinator:
    def __init__(self, service: CatalogIntakeSubmissionService, dispatcher) -> None:
        self.service = service
        self.dispatcher = dispatcher

    def start(self, intake_id: str, *, requested_by: str) -> CatalogIntakeDraft:
        if not self.dispatcher.available:
            raise ValueError("isolated discovery worker is not available")
        queued = self.service.start_discovery(intake_id, requested_by=requested_by)
        approval = queued.source_approval
        execution = queued.discovery_execution
        assert approval is not None and execution is not None
        request = CatalogIntakeDiscoveryRequest(
            intake_id=intake_id,
            attempt_id=execution.attempt_id,
            repository_url=queued.release_identity.repository_url,
            revision=queued.release_identity.revision,
            catalog_item_id=queued.requested.catalog_item_id,
            display_name=queued.requested.display_name,
            policy_version="1.0.0",
            source_approval_id=approval.approval_id,
            worker_image_digest=self.dispatcher.worker_image_digest,
        )
        try:
            self.dispatcher.dispatch(request, approval)
        except Exception:  # noqa: BLE001 - never persist dispatcher exception text
            self.service.mark_discovery_failed(intake_id, ["dispatch-failed"])
            raise ValueError("discovery dispatch failed") from None
        return self.service.mark_discovery_running(intake_id)

    def collect(self, receipt: CatalogIntakeDiscoveryReceipt) -> CatalogIntakeDraft:
        draft = self.service.get(receipt.intake_id)
        if draft is None:
            raise KeyError(receipt.intake_id)
        if draft.discovery is not None:
            if receipt.status != "passed":
                raise ValueError("completed discovery cannot accept a failed receipt")
            return self.service.record_discovery(receipt.intake_id, receipt)
        execution = draft.discovery_execution
        if execution is None or execution.attempt_id != receipt.attempt_id:
            raise ValueError("discovery receipt attempt identity does not match")
        if (
            receipt.repository_url != draft.release_identity.repository_url
            or receipt.revision != draft.release_identity.revision
        ):
            raise ValueError("discovery receipt repository identity does not match")
        if receipt.status != "passed":
            return self.service.mark_discovery_failed(
                receipt.intake_id, receipt.error_codes or ["worker-failed"]
            )
        return self.service.record_discovery(receipt.intake_id, receipt)
