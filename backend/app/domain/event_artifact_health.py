"""Trusted inputs and observed cold-pull evidence for event artifact readiness."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

IMMUTABLE_IMAGE_REF = r"^\S+@sha256:[0-9a-f]{64}$"


class ArtifactReadinessRequirement(BaseModel):
    """Server-side expectation from release and current placement evidence.

    The snapshot producer must not define the expected image or node set.
    """

    model_config = ConfigDict(extra="forbid")

    cluster_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    image_refs: list[str] = Field(min_length=1)
    expected_node_ids: list[str] = Field(min_length=1)
    minimum_cold_samples: int = Field(default=3, ge=1)
    maximum_cold_pull_p95_seconds: float = Field(default=180, gt=0)

    @model_validator(mode="after")
    def valid_expectations(self) -> "ArtifactReadinessRequirement":
        import re

        if any(not re.fullmatch(IMMUTABLE_IMAGE_REF, ref) for ref in self.image_refs):
            raise ValueError("artifact requirements must use immutable image digests")
        if len(self.image_refs) != len(set(self.image_refs)):
            raise ValueError("duplicate expected image")
        if any(not node.strip() for node in self.expected_node_ids):
            raise ValueError("empty expected node")
        if len(self.expected_node_ids) != len(set(self.expected_node_ids)):
            raise ValueError("duplicate expected node")
        return self


class ArtifactColdPullEvidence(BaseModel):
    """Observed pull on one destination node, not merely image publication."""

    model_config = ConfigDict(extra="forbid")

    image_ref: str = Field(pattern=IMMUTABLE_IMAGE_REF)
    node_id: str = Field(min_length=1)
    cold_cache_verified: bool
    cold_samples: int = Field(ge=0)
    failures: int = Field(ge=0)
    cold_pull_p95_seconds: float = Field(ge=0)
    digest_verified: bool
    signature_verified: bool


class ArtifactReleaseReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    registry_reachable: bool
    pulls: list[ArtifactColdPullEvidence]

    @model_validator(mode="after")
    def unique_pulls(self) -> "ArtifactReleaseReadiness":
        keys = [(pull.image_ref, pull.node_id) for pull in self.pulls]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate image/node cold-pull evidence")
        return self


class EventArtifactHealthSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observed_at: datetime
    releases: list[ArtifactReleaseReadiness]

    @model_validator(mode="after")
    def unique_releases(self) -> "EventArtifactHealthSnapshot":
        if self.observed_at.tzinfo is None:
            raise ValueError("artifact health observed_at must include a timezone")
        keys = [(row.cluster_id, row.catalog_id, row.catalog_release) for row in self.releases]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate cluster/catalog/release artifact evidence")
        return self
