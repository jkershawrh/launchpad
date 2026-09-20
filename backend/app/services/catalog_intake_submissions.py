from __future__ import annotations

import hashlib
import json
import os

from app.domain.catalog_intake import (
    CatalogIntakeDiscoverySummary,
    CatalogIntakeDraft,
    CatalogIntakeEvidence,
    CatalogIntakeReleaseIdentity,
    CatalogIntakeSubmission,
)
from app.domain.catalog_intake_discovery import CatalogIntakeDiscoveryReceipt
from app.services.catalog_onboarding import (
    DISCOVERY_RECEIPT_VERSION,
    build_catalog_draft_from_receipt,
)
from app.storage.catalog_intakes import (
    CatalogIntakeDraftStore,
    InMemoryCatalogIntakeDraftStore,
    PostgresCatalogIntakeDraftStore,
)

REQUIRED_GATES = [
    "repository-discovery",
    "content-build",
    "artifact-policy",
    "security-review",
    "model-compatibility",
    "one-seat-lifecycle",
    "restart-recovery",
    "zero-residue-reclaim",
    "supported-target-qualification",
    "promotion-approval",
]


class CatalogIntakeSubmissionService:
    """Draft registry with no live catalog or cluster dependency."""

    def __init__(self, store: CatalogIntakeDraftStore | None = None) -> None:
        self.store = store or InMemoryCatalogIntakeDraftStore()

    @staticmethod
    def _normalize(submission: CatalogIntakeSubmission) -> CatalogIntakeSubmission:
        payload = submission.model_dump()
        payload["audience"] = sorted(set(payload["audience"]))
        return CatalogIntakeSubmission(**payload)

    @staticmethod
    def _identity(submission: CatalogIntakeSubmission) -> str:
        canonical = json.dumps(
            submission.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return f"intake-{hashlib.sha256(canonical).hexdigest()[:20]}"

    def submit(self, submission: CatalogIntakeSubmission) -> CatalogIntakeDraft:
        normalized = self._normalize(submission)
        intake_id = self._identity(normalized)
        blockers = [
            "Immutable repository discovery and static inventory have not been run.",
            "Generated catalog draft and deployment package have not been reviewed.",
            "Artifact, security, content, and model compatibility gates have not passed.",
            "No execution cluster has been qualified as a supported target.",
            "One-seat lifecycle, restart recovery, and zero-residue reclaim are unproven.",
            "Human approval and rollback metadata are not recorded.",
        ]
        if not self.store.durable:
            blockers.append(
                "Durable intake persistence and multi-replica consistency are not certified."
            )
        if normalized.expected_scale > 1:
            blockers.append(
                f"Requested {normalized.expected_scale}-seat scale exceeds the draft's "
                "one-seat ceiling and requires progressive certification."
            )
        draft = CatalogIntakeDraft(
            intake_id=intake_id,
            storage_scope=(
                "durable-postgres" if self.store.durable else "process-local-draft"
            ),
            requested=normalized,
            blockers=blockers,
            evidence=CatalogIntakeEvidence(required_gates=REQUIRED_GATES),
            release_identity=CatalogIntakeReleaseIdentity(
                repository_url=normalized.repository_url,
                revision=normalized.revision,
            ),
        )
        return self.store.create_idempotent(draft)

    def get(self, intake_id: str) -> CatalogIntakeDraft | None:
        return self.store.get(intake_id)

    def list_all(self) -> list[CatalogIntakeDraft]:
        return self.store.list_all()

    def record_discovery(
        self,
        intake_id: str,
        receipt: CatalogIntakeDiscoveryReceipt,
    ) -> CatalogIntakeDraft:
        """Attach one trusted discovery result and create its review-only preview."""

        draft = self.store.get(intake_id)
        if draft is None:
            raise KeyError(intake_id)
        if receipt.intake_id != intake_id:
            raise ValueError("discovery receipt intake identity does not match")
        if (
            receipt.repository_url != draft.release_identity.repository_url
            or receipt.revision != draft.release_identity.revision
        ):
            raise ValueError("discovery receipt repository identity does not match")
        if (
            receipt.status != "passed"
            or receipt.error_codes
            or receipt.draft_intake is None
            or receipt.output_hash is None
            or receipt.cleanup.result != "pass"
            or not receipt.cleanup.workspace_removed
        ):
            raise ValueError("catalog review requires a successful discovery receipt")

        encoded = json.dumps(
            receipt.draft_intake,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        expected_hash = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if receipt.output_hash != expected_hash:
            raise ValueError("discovery receipt output hash does not match")

        if draft.discovery is not None:
            if (
                draft.discovery.attempt_id == receipt.attempt_id
                and draft.discovery.output_hash == receipt.output_hash
            ):
                return draft
            raise ValueError("catalog intake already has a different discovery result")

        discovered_catalog = receipt.draft_intake.get("catalog") or {}
        if discovered_catalog.get("catalog_item_id") != draft.requested.catalog_item_id:
            raise ValueError("discovered catalog identity does not match intake")
        inventory = (receipt.draft_intake.get("discovery") or {}).get("inventory")
        compatibility_receipt = {
            "schema": DISCOVERY_RECEIPT_VERSION,
            "discovery_status": "pass",
            "catalog_item_id": draft.requested.catalog_item_id,
            "repo_url": receipt.repository_url,
            "revision": receipt.revision,
            "inventory": inventory,
            "draft_intake": receipt.draft_intake,
            "errors": [],
        }
        preview = build_catalog_draft_from_receipt(compatibility_receipt)
        if preview.get("status") != "draft":
            raise ValueError("discovery may produce only a draft catalog preview")

        resolved = {
            "Immutable repository discovery and static inventory have not been run.",
            "Generated catalog draft and deployment package have not been reviewed.",
        }
        blockers = [item for item in draft.blockers if item not in resolved]
        blockers.extend(
            (receipt.draft_intake.get("certification") or {}).get(
                "activation_blockers", []
            )
        )
        blockers = list(dict.fromkeys(blockers))
        updated = draft.model_copy(
            update={
                "blockers": blockers,
                "discovery": CatalogIntakeDiscoverySummary(
                    attempt_id=receipt.attempt_id,
                    output_hash=receipt.output_hash,
                    worker_image_digest=receipt.worker_image_digest,
                    files_scanned=receipt.scan_summary.get("files_scanned", 0),
                    bytes_scanned=receipt.scan_summary.get("bytes_scanned", 0),
                    cleanup_verified=True,
                ),
                "catalog_preview": preview,
                "evidence": draft.evidence.model_copy(
                    update={
                        "status": "partial",
                        "artifacts": [
                            f"discovery-receipt:{receipt.attempt_id}",
                            f"catalog-preview:{receipt.output_hash}",
                        ],
                    }
                ),
            }
        )
        validated = CatalogIntakeDraft.model_validate(updated.model_dump())
        return self.store.replace(draft, validated)

    def clear(self) -> None:
        """Clear local drafts for deterministic tests; never touches catalog state."""
        clear = getattr(self.store, "clear", None)
        if clear is None:
            raise RuntimeError("Durable catalog intake storage cannot be cleared through the API")
        clear()


def create_catalog_intake_submission_service(
    *,
    mode: str | None = None,
    database_url: str | None = None,
    ha_enabled: bool | None = None,
) -> CatalogIntakeSubmissionService:
    """Choose durable storage, refusing unsafe HA/non-local fallback."""
    selected_mode = mode or os.environ.get("LAUNCHPAD_MODE", "mock")
    selected_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL")
    )
    selected_ha = (
        ha_enabled
        if ha_enabled is not None
        else os.environ.get("LIFECYCLE_HA_ENABLED", "false").lower() == "true"
    )
    if selected_url:
        return CatalogIntakeSubmissionService(
            store=PostgresCatalogIntakeDraftStore(selected_url)
        )
    if selected_ha:
        raise RuntimeError("Catalog intake HA mode requires durable PostgreSQL storage")
    if selected_mode not in {"mock", "local", "test"}:
        raise RuntimeError(
            "Catalog intake outside local/test mode requires durable PostgreSQL storage"
        )
    return CatalogIntakeSubmissionService(store=InMemoryCatalogIntakeDraftStore())
