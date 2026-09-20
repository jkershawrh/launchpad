from __future__ import annotations

import hashlib
import json
import os

from app.domain.catalog_intake import (
    CatalogIntakeDraft,
    CatalogIntakeEvidence,
    CatalogIntakeReleaseIdentity,
    CatalogIntakeSubmission,
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
