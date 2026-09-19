from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class AcmClusterObservation(BaseModel):
    cluster_id: str = Field(min_length=1)
    resource_version: str = ""
    available: bool
    hub_accepted: bool
    acm_eligible: bool
    reasons: list[str] = Field(default_factory=list)
    decision_reasons: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    claims: dict[str, str] = Field(default_factory=dict)


class AcmPlacementSnapshot(BaseModel):
    namespace: str = Field(min_length=1)
    placement_name: str = Field(min_length=1)
    snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    clusters: list[AcmClusterObservation] = Field(default_factory=list)

    @property
    def eligible_cluster_ids(self) -> list[str]:
        return [item.cluster_id for item in self.clusters if item.acm_eligible]
