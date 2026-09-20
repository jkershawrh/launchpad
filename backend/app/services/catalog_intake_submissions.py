from __future__ import annotations

import hashlib
import json
from threading import RLock

from app.domain.catalog_intake import (
    CatalogIntakeDraft,
    CatalogIntakeEvidence,
    CatalogIntakeReleaseIdentity,
    CatalogIntakeSubmission,
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
    """Process-local draft registry with no live catalog or cluster dependency."""

    def __init__(self) -> None:
        self._drafts: dict[str, CatalogIntakeDraft] = {}
        self._lock = RLock()

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
            "Durable intake persistence and multi-replica consistency are not certified.",
        ]
        if normalized.expected_scale > 1:
            blockers.append(
                f"Requested {normalized.expected_scale}-seat scale exceeds the draft's "
                "one-seat ceiling and requires progressive certification."
            )
        draft = CatalogIntakeDraft(
            intake_id=intake_id,
            requested=normalized,
            blockers=blockers,
            evidence=CatalogIntakeEvidence(required_gates=REQUIRED_GATES),
            release_identity=CatalogIntakeReleaseIdentity(
                repository_url=normalized.repository_url,
                revision=normalized.revision,
            ),
        )
        with self._lock:
            existing = self._drafts.setdefault(intake_id, draft)
            return existing.model_copy(deep=True)

    def get(self, intake_id: str) -> CatalogIntakeDraft | None:
        with self._lock:
            draft = self._drafts.get(intake_id)
            return draft.model_copy(deep=True) if draft else None

    def list_all(self) -> list[CatalogIntakeDraft]:
        with self._lock:
            return [
                self._drafts[intake_id].model_copy(deep=True)
                for intake_id in sorted(self._drafts)
            ]

    def clear(self) -> None:
        """Clear local drafts for deterministic tests; never touches catalog state."""
        with self._lock:
            self._drafts.clear()
