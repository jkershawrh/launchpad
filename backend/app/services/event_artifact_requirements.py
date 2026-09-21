"""Resolve cold-pull expectations from server-trusted release and placement sources.

This boundary deliberately has no requester- or observation-snapshot argument.
The concrete source adapters must authenticate the promoted release registry and
current scheduler/node inventory before they are wired into admission.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.event_artifact_health import ArtifactReadinessRequirement
from app.domain.events import EventRecord

MAX_PLACEMENT_AGE_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 30
_DIGEST = r"^sha256:[0-9a-f]{64}$"


class ArtifactRequirementSourceError(ValueError):
    """Trusted inputs cannot prove the exact release and node set."""


class TrustedReleaseManifest(BaseModel):
    """Result from a server-owned, promoted release manifest resolver."""

    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    image_refs: list[str] = Field(min_length=1)
    promotion_evidence_id: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def immutable_unique_images(self) -> TrustedReleaseManifest:
        # Reuse the expectation model's strict immutable digest policy.
        ArtifactReadinessRequirement(
            cluster_id="validation",
            catalog_id=self.catalog_id,
            catalog_release=self.catalog_release,
            image_refs=self.image_refs,
            expected_node_ids=["validation"],
        )
        return self


class TrustedEligibleNodes(BaseModel):
    """Result from a server-owned placement/eligible-node inventory."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=1)
    observed_at: datetime

    @model_validator(mode="after")
    def unique_nodes_and_aware_time(self) -> TrustedEligibleNodes:
        if self.observed_at.tzinfo is None:
            raise ValueError("eligible-node observation must include a timezone")
        if any(not node.strip() for node in self.node_ids):
            raise ValueError("eligible-node ID must not be empty")
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("eligible-node IDs must be unique")
        return self


class PromotedReleaseSource(Protocol):
    """Authenticated adapter for promoted, immutable catalog release records."""

    def get_promoted_release(
        self, catalog_id: str, catalog_release: str
    ) -> TrustedReleaseManifest | None: ...


class EligibleNodeSource(Protocol):
    """Authenticated adapter for current scheduling eligibility."""

    def get_eligible_nodes(
        self, cluster_id: str, catalog_id: str, catalog_release: str
    ) -> TrustedEligibleNodes | None: ...


def build_event_artifact_requirements(
    record: EventRecord,
    releases: PromotedReleaseSource,
    nodes: EligibleNodeSource,
    *,
    now: datetime,
) -> list[ArtifactReadinessRequirement]:
    """Build exact release/image/node requirements for persisted allocations.

    Fail closed on incomplete allocation coverage, unpromoted/mutable images,
    missing eligibility, or stale placement. No cold-pull evidence is read here.
    """

    if now.tzinfo is None:
        raise ValueError("requirement assessment time must include a timezone")
    if not record.capacity_preview.eligible:
        raise ArtifactRequirementSourceError("event capacity preview is ineligible")

    labs = {lab.lab_ref: lab for lab in record.manifest.labs}
    expected = {
        (cohort.cohort_id, lab_ref)
        for cohort in record.manifest.cohorts
        for lab_ref in cohort.lab_refs
    }
    allocations = record.capacity_preview.allocations
    actual = [(allocation.cohort_id, allocation.lab_ref) for allocation in allocations]
    if not expected or len(actual) != len(set(actual)) or set(actual) != expected:
        raise ArtifactRequirementSourceError(
            "event allocations do not cover exact cohort/lab pairs"
        )

    keys: set[tuple[str, str, str]] = set()
    for allocation in allocations:
        lab = labs[allocation.lab_ref]
        if (allocation.catalog_id, allocation.catalog_release) != (
            lab.catalog_id,
            lab.catalog_release,
        ) or not allocation.cluster_id.strip():
            raise ArtifactRequirementSourceError("allocation does not match exact catalog release")
        keys.add((allocation.cluster_id, allocation.catalog_id, allocation.catalog_release))

    result: list[ArtifactReadinessRequirement] = []
    for cluster_id, catalog_id, catalog_release in sorted(keys):
        label = f"{cluster_id}/{catalog_id}@{catalog_release}"
        try:
            release = releases.get_promoted_release(catalog_id, catalog_release)
            placement = nodes.get_eligible_nodes(cluster_id, catalog_id, catalog_release)
            if release is None or placement is None:
                raise ArtifactRequirementSourceError(
                    f"trusted release or placement is missing: {label}"
                )
            # Validate again because mutable Pydantic objects can be altered or
            # copied without validation by an adapter after initial construction.
            release = TrustedReleaseManifest.model_validate(release.model_dump())
            placement = TrustedEligibleNodes.model_validate(placement.model_dump())
            if (release.catalog_id, release.catalog_release) != (catalog_id, catalog_release):
                raise ArtifactRequirementSourceError(
                    f"promoted release identity mismatches: {label}"
                )
            if (placement.cluster_id, placement.catalog_id, placement.catalog_release) != (
                cluster_id,
                catalog_id,
                catalog_release,
            ):
                raise ArtifactRequirementSourceError(f"eligible-node identity mismatches: {label}")
            age = (now - placement.observed_at).total_seconds()
            if age > MAX_PLACEMENT_AGE_SECONDS or age < -MAX_FUTURE_SKEW_SECONDS:
                raise ArtifactRequirementSourceError(
                    f"eligible-node evidence is stale or future-dated: {label}"
                )
            result.append(
                ArtifactReadinessRequirement(
                    cluster_id=cluster_id,
                    catalog_id=catalog_id,
                    catalog_release=catalog_release,
                    image_refs=sorted(release.image_refs),
                    expected_node_ids=sorted(placement.node_ids),
                )
            )
        except ArtifactRequirementSourceError:
            raise
        except (AttributeError, TypeError, ValueError) as exc:
            raise ArtifactRequirementSourceError(
                f"invalid trusted artifact input: {label}"
            ) from exc

    return result
