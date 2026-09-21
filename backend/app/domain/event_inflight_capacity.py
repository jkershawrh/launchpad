"""Short-lived, server-owned physical resource accounting for event admission.

The snapshot is evidence, not an admission decision. Reservation accounting and
the certified capacity matrix remain separate gates.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class InflightResourceVector(BaseModel):
    cpu_millicores: int = Field(default=0, ge=0)
    memory_mib: int = Field(default=0, ge=0)
    pods: int = Field(default=0, ge=0)
    model_slots: int = Field(default=0, ge=0)


class InflightWorkloadUsage(BaseModel):
    """Observed allocation in one namespace, optionally owned by a reservation."""

    namespace: str = Field(min_length=1)
    reservation_id: str | None = None
    workshop_id: str | None = None
    seat_refs: list[str] = Field(default_factory=list)
    resources: InflightResourceVector

    @model_validator(mode="after")
    def valid_identity(self) -> InflightWorkloadUsage:
        if self.reservation_id is None and (self.workshop_id or self.seat_refs):
            raise ValueError("external workload cannot claim workshop or seat identity")
        if any(not seat.strip() for seat in self.seat_refs):
            raise ValueError("seat references must be non-empty")
        return self


class InflightClusterUsage(BaseModel):
    cluster_id: str = Field(min_length=1)
    allocatable: InflightResourceVector
    accounting_complete: bool
    workloads: list[InflightWorkloadUsage] = Field(default_factory=list)


class EventInflightCapacitySnapshot(BaseModel):
    snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observed_at: datetime
    clusters: list[InflightClusterUsage]

    @model_validator(mode="after")
    def valid_snapshot(self) -> EventInflightCapacitySnapshot:
        if self.observed_at.tzinfo is None:
            raise ValueError("in-flight observed_at must include a timezone")
        ids = [cluster.cluster_id for cluster in self.clusters]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate cluster in in-flight capacity evidence")
        return self
