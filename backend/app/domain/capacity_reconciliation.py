"""Versioned, offline capacity forecast and reconciliation records.

These models describe only facts present in immutable event inputs and recorded
postmortems.  Missing operational measurements remain explicitly unavailable;
they are never represented as observed zeroes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.events import EventManifest


class CapacityMeasurement(BaseModel):
    status: Literal["available", "unavailable"]
    value: int | float | str | None = None
    unit: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def availability_is_truthful(self) -> CapacityMeasurement:
        if self.status == "unavailable":
            if self.value is not None:
                raise ValueError("unavailable measurement must not carry a value")
            if not self.reason or not self.reason.strip():
                raise ValueError("unavailable measurement requires a reason")
        elif self.value is None:
            raise ValueError("available measurement requires a value")
        return self


class RecordedEventManifest(BaseModel):
    api_version: str
    kind: Literal["EventManifest"]
    spec: EventManifest


class RecordedPostmortemSummary(BaseModel):
    waves: int = Field(ge=1)
    workshops_ordered: int = Field(ge=1)
    workshops_ready_retained: int = Field(ge=0)
    workshops_reclaimed: int = Field(ge=0)
    seats_provisioned: int = Field(ge=0)
    seats_claimed: int = Field(ge=0)
    seats_unclaimed: int = Field(ge=0)
    claim_utilization_percent: float = Field(ge=0, le=100)


class RecordedCatalogObservation(BaseModel):
    name: str = Field(min_length=1)
    ordered: int = Field(ge=0)
    claimed: int = Field(ge=0)
    unclaimed: int = Field(ge=0)
    claim_percent: float = Field(ge=0, le=100)


class RecordedWaveObservation(BaseModel):
    wave: int = Field(ge=1)
    ordered: int = Field(ge=0)
    claimed: int = Field(ge=0)
    unclaimed: int = Field(ge=0)
    claim_percent: float = Field(ge=0, le=100)


class RecordedWorkshopObservation(BaseModel):
    wave: int = Field(ge=1)
    catalog: str = Field(min_length=1)
    cluster: str = Field(min_length=1)
    workshop: str = Field(min_length=1)
    claimed: int = Field(ge=0)
    ordered: int = Field(ge=0)
    state: str = Field(min_length=1)
    expires: datetime


class RecordedClusterObservation(BaseModel):
    name: str = Field(min_length=1)
    seats: int = Field(ge=0)
    claimed: int = Field(ge=0)
    pods_ready: int = Field(ge=0)
    pods_total: int = Field(ge=0)
    routes_admitted: int = Field(ge=0)
    routes_total: int = Field(ge=0)
    restarts: int = Field(ge=0)
    note: str = ""


class RecordedModelObservation(BaseModel):
    name: str = Field(min_length=1)
    ready: int = Field(ge=0)
    desired: int = Field(ge=0)


class RecordedPilotPostmortem(BaseModel):
    schema_version: int
    snapshot_at: datetime
    event: str = Field(min_length=1)
    summary: RecordedPostmortemSummary
    catalogs: list[RecordedCatalogObservation]
    waves: list[RecordedWaveObservation]
    workshops: list[RecordedWorkshopObservation]
    clusters: list[RecordedClusterObservation]
    models: list[RecordedModelObservation]
    telemetry: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def recorded_totals_are_consistent(self) -> RecordedPilotPostmortem:
        summary = self.summary
        failures: list[str] = []
        if summary.seats_claimed + summary.seats_unclaimed != summary.seats_provisioned:
            failures.append("claimed and unclaimed seats do not equal provisioned seats")
        if len(self.workshops) != summary.workshops_ordered:
            failures.append("workshop records do not equal workshops ordered")
        if len(self.waves) != summary.waves:
            failures.append("wave records do not equal recorded waves")
        for label, records in (("catalog", self.catalogs), ("wave", self.waves)):
            if sum(item.ordered for item in records) != summary.seats_provisioned:
                failures.append(f"{label} ordered seats do not equal provisioned seats")
            if sum(item.claimed for item in records) != summary.seats_claimed:
                failures.append(f"{label} claimed seats do not equal claimed seats")
            if sum(item.unclaimed for item in records) != summary.seats_unclaimed:
                failures.append(f"{label} unclaimed seats do not equal unclaimed seats")
        if sum(item.ordered for item in self.workshops) != summary.seats_provisioned:
            failures.append("workshop ordered seats do not equal provisioned seats")
        if sum(item.seats for item in self.clusters) != summary.seats_provisioned:
            failures.append("cluster seats do not equal provisioned seats")
        if failures:
            raise ValueError("recorded postmortem is inconsistent: " + "; ".join(failures))
        return self


class CapacityEvidenceSource(BaseModel):
    role: Literal["forecast", "observed"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ForecastCatalog(BaseModel):
    lab_ref: str
    catalog_id: str
    catalog_release: str
    seat_environments: int = Field(ge=0)


class CapacityForecast(BaseModel):
    cohort_count: int = Field(ge=1)
    participant_count: int = Field(ge=1)
    workshop_count: int = Field(ge=1)
    seat_environments: int = Field(ge=1)
    peak_concurrent_participants: int = Field(ge=1)
    peak_retained_environments: int = Field(ge=1)
    retention_hours: int = Field(ge=1)
    provisioning_waves: CapacityMeasurement
    wave_schedule: CapacityMeasurement
    deployment_class: CapacityMeasurement
    catalogs: list[ForecastCatalog]


class ObservedCatalog(BaseModel):
    catalog_label: str
    catalog_id: CapacityMeasurement
    ordered: int = Field(ge=0)
    claimed: int = Field(ge=0)
    unclaimed: int = Field(ge=0)
    claim_percent: float = Field(ge=0, le=100)


class ObservedCapacity(BaseModel):
    waves: int = Field(ge=1)
    workshops_ordered: int = Field(ge=1)
    workshops_ready_retained: int = Field(ge=0)
    workshops_reclaimed: int = Field(ge=0)
    seats_provisioned: int = Field(ge=0)
    seats_claimed: int = Field(ge=0)
    seats_unclaimed: int = Field(ge=0)
    claim_utilization_percent: float = Field(ge=0, le=100)
    catalogs: list[ObservedCatalog]
    clusters: list[RecordedClusterObservation]
    models: list[RecordedModelObservation]
    reservations: CapacityMeasurement
    actual_cpu_millicore_hours: CapacityMeasurement
    actual_memory_mib_hours: CapacityMeasurement
    actual_storage_gib_hours: CapacityMeasurement
    model_requests: CapacityMeasurement
    model_input_tokens: CapacityMeasurement
    model_output_tokens: CapacityMeasurement
    model_queue_seconds: CapacityMeasurement
    image_cache_hit_rate: CapacityMeasurement


class CapacityVariance(BaseModel):
    provisioned_seat_environments: int
    workshop_count: int
    unclaimed_seat_environments: int = Field(ge=0)
    claim_utilization_percent: float = Field(ge=0, le=100)
    reservation_variance: CapacityMeasurement
    actual_resource_variance: CapacityMeasurement
    model_demand_variance: CapacityMeasurement


class CapacityReconciliation(BaseModel):
    schema_version: Literal["launchpad.intel.com/capacity-reconciliation/v1"]
    event_id: str = Field(min_length=1)
    observed_at: datetime
    sources: list[CapacityEvidenceSource] = Field(min_length=2)
    forecast: CapacityForecast
    observed: ObservedCapacity
    variance: CapacityVariance
    limitations: list[str] = Field(min_length=1)
