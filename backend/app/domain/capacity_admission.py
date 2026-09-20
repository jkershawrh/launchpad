"""Pure aggregate workshop-capacity admission domain records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.events import EventResourceVector


class InferenceCapacity(BaseModel):
    model_id: str = Field(min_length=1)
    model_release: str = Field(min_length=1)
    concurrent_requests: int = Field(default=0, ge=0)
    input_tokens_per_minute: int = Field(default=0, ge=0)
    output_tokens_per_minute: int = Field(default=0, ge=0)

    def scaled(self, count: int) -> InferenceCapacity:
        if count < 0:
            raise ValueError("inference multiplier must be non-negative")
        return self.model_copy(
            update={
                "concurrent_requests": self.concurrent_requests * count,
                "input_tokens_per_minute": self.input_tokens_per_minute * count,
                "output_tokens_per_minute": self.output_tokens_per_minute * count,
            }
        )


class CapacityEnvelope(BaseModel):
    infrastructure: EventResourceVector
    inference: InferenceCapacity


class CapacitySupplySnapshot(BaseModel):
    snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy_id: str = Field(min_length=1)
    cluster_ref: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    eligible: bool
    infrastructure: EventResourceVector
    inference: InferenceCapacity
    observed_at: datetime
    valid_until: datetime

    @model_validator(mode="after")
    def timestamps_are_bounded(self) -> CapacitySupplySnapshot:
        if self.observed_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("capacity supply timestamps must include a timezone")
        if self.valid_until <= self.observed_at:
            raise ValueError("capacity supply validity must end after observation")
        return self


class WorkshopCapacityRequest(BaseModel):
    request_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    forecast_ref: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    workshop_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    cluster_ref: str = Field(min_length=1)
    placement_policy: Literal["single_cluster_per_workshop"] = "single_cluster_per_workshop"
    seats: int = Field(ge=1)
    infrastructure_per_seat: EventResourceVector
    inference_per_seat: InferenceCapacity
    requested_at: datetime

    @model_validator(mode="after")
    def request_is_atomic_and_timestamped(self) -> WorkshopCapacityRequest:
        if self.requested_at.tzinfo is None:
            raise ValueError("capacity request timestamp must include a timezone")
        if self.infrastructure_per_seat.seats != 1:
            raise ValueError("per-seat infrastructure must declare exactly one seat")
        return self

    @property
    def demand(self) -> CapacityEnvelope:
        return CapacityEnvelope(
            infrastructure=self.infrastructure_per_seat.scaled(self.seats),
            inference=self.inference_per_seat.scaled(self.seats),
        )


class CapacityAdmissionDecision(BaseModel):
    decision_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    request_id: str
    idempotency_key: str
    request_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    forecast_ref: str
    event_id: str
    workshop_id: str
    catalog_id: str
    catalog_release: str
    cluster_ref: str
    model_id: str
    model_release: str
    supply_snapshot_id: str
    policy_id: str
    status: Literal["accepted", "rejected"]
    reason_codes: list[str] = Field(default_factory=list)
    limiting_dimensions: list[str] = Field(default_factory=list)
    requested_seats: int = Field(ge=1)
    reserved_seats: int = Field(ge=0)
    demand: CapacityEnvelope
    remaining_before: CapacityEnvelope
    remaining_after: CapacityEnvelope
    reservation_id: str | None = None
    decided_at: datetime

    @model_validator(mode="after")
    def outcome_is_atomic(self) -> CapacityAdmissionDecision:
        if self.status == "accepted":
            if self.reserved_seats != self.requested_seats or not self.reservation_id:
                raise ValueError("accepted decision must reserve the whole workshop")
            if self.reason_codes or self.limiting_dimensions:
                raise ValueError("accepted decision cannot carry rejection reasons")
        elif self.reserved_seats != 0 or self.reservation_id is not None:
            raise ValueError("rejected decision cannot reserve partial capacity")
        return self


class AggregateCapacityReservation(BaseModel):
    reservation_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str
    request_fingerprint: str
    forecast_ref: str
    event_id: str
    workshop_id: str
    catalog_id: str
    catalog_release: str
    cluster_ref: str
    model_id: str
    model_release: str
    supply_snapshot_id: str
    policy_id: str
    resources: CapacityEnvelope
    status: Literal["held", "released"] = "held"
    created_at: datetime
    released_at: datetime | None = None
    cleanup_evidence_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def release_has_evidence(self) -> AggregateCapacityReservation:
        if self.status == "released":
            if self.released_at is None or not self.cleanup_evidence_id:
                raise ValueError("released reservation requires cleanup evidence")
        elif self.released_at is not None or self.cleanup_evidence_id is not None:
            raise ValueError("held reservation cannot carry release evidence")
        return self


class CapacityAdmissionRecord(BaseModel):
    decision_id: str
    reservation_id: str | None
    forecast_ref: str
    event_id: str
    workshop_id: str
    catalog_id: str
    catalog_release: str
    cluster_ref: str
    model_id: str
    model_release: str
    supply_snapshot_id: str
    policy_id: str
    decision_status: Literal["accepted", "rejected"]
    reservation_status: Literal["held", "released"] | None
    requested_seats: int = Field(ge=1)
    reserved_seats: int = Field(ge=0)
    reason_codes: list[str]
    limiting_dimensions: list[str]
    requested_resources: CapacityEnvelope
    cleanup_evidence_id: str | None
    decided_at: datetime
    released_at: datetime | None


class CapacityReconciliationSnapshot(BaseModel):
    schema_version: Literal["launchpad.intel.com/capacity-admission-reconciliation/v1"]
    supply_snapshot_id: str
    policy_id: str
    cluster_ref: str
    model_id: str
    model_release: str
    status: Literal["balanced", "overcommitted"]
    active_reservations: int = Field(ge=0)
    active_seats: int = Field(ge=0)
    active_infrastructure: EventResourceVector
    active_inference: InferenceCapacity
    exceeded_dimensions: list[str]
    records: list[CapacityAdmissionRecord]
    observed_at: datetime
