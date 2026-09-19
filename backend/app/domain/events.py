from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EventCohort(BaseModel):
    cohort_id: str = Field(min_length=1)
    participants: int = Field(ge=1)
    lab_refs: list[str] = Field(min_length=1)
    starts_at: datetime | None = None

    @model_validator(mode="after")
    def unique_labs(self) -> EventCohort:
        if len(self.lab_refs) != len(set(self.lab_refs)):
            raise ValueError(f"Cohort {self.cohort_id} contains duplicate lab references")
        return self


class EventLab(BaseModel):
    lab_ref: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    required_capabilities: list[str] = Field(default_factory=list)


class EventRetention(BaseModel):
    hours: int = Field(ge=1)
    starts_from: Literal["event_start", "cohort_start", "claim"]


class EventApproval(BaseModel):
    event_owner_approved: bool
    technical_approver_approved: bool
    approved_seat_environments: int = Field(ge=1)
    approved_retention_hours: int = Field(ge=1)
    approved_at: datetime | None = None


class EventManifest(BaseModel):
    event_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    technical_approver: str = Field(min_length=1)
    exposure_policy: Literal["internal", "public_code"]
    cohorts: list[EventCohort] = Field(min_length=1)
    labs: list[EventLab] = Field(min_length=1)
    retention: EventRetention
    approval: EventApproval

    @model_validator(mode="after")
    def references_are_consistent(self) -> EventManifest:
        cohort_ids = [cohort.cohort_id for cohort in self.cohorts]
        if len(cohort_ids) != len(set(cohort_ids)):
            raise ValueError("Event cohort IDs must be unique")

        lab_ids = [lab.lab_ref for lab in self.labs]
        if len(lab_ids) != len(set(lab_ids)):
            raise ValueError("Event lab references must be unique")

        unknown = sorted(
            {
                lab_ref
                for cohort in self.cohorts
                for lab_ref in cohort.lab_refs
                if lab_ref not in set(lab_ids)
            }
        )
        if unknown:
            raise ValueError(f"Unknown event lab references: {', '.join(unknown)}")
        return self


class EventCapacitySupply(BaseModel):
    """Server-owned capacity categories.

    Only ``certified_capacity`` can satisfy normal event demand. DR-reserved and
    uncertified capacity are reported so an operator can see theoretical
    headroom without accidentally making it placeable.
    """

    certified_capacity: int = Field(default=0, ge=0)
    dr_reserved_capacity: int = Field(default=0, ge=0)
    uncertified_capacity: int = Field(default=0, ge=0)


class EventCapacityPreview(BaseModel):
    participant_count: int
    seat_environments: int
    peak_concurrent_participants: int
    peak_retained_environments: int
    certified_capacity: int
    dr_reserved_capacity: int
    uncertified_capacity: int
    capacity_shortfall: int
    eligible: bool
    explanation: str


class EventRecord(BaseModel):
    manifest: EventManifest
    capacity_preview: EventCapacityPreview
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventManifestConflictError(RuntimeError):
    """Raised when an immutable event ID has already been persisted."""


def calculate_event_capacity(
    manifest: EventManifest,
    supply: EventCapacitySupply,
) -> EventCapacityPreview:
    """Calculate conservative event demand without mutating lifecycle state."""

    participant_count = sum(cohort.participants for cohort in manifest.cohorts)
    seat_environments = sum(
        cohort.participants * len(cohort.lab_refs) for cohort in manifest.cohorts
    )
    peak_concurrent_participants = max(
        cohort.participants for cohort in manifest.cohorts
    )

    # Until the scheduler has explicit end times and reuse policy, retained
    # event capacity is conservatively assumed to accumulate across cohorts.
    peak_retained_environments = seat_environments

    approval = manifest.approval
    if not approval.event_owner_approved or not approval.technical_approver_approved:
        raise ValueError("Event owner and technical approver must both approve the manifest")
    if approval.approved_seat_environments != seat_environments:
        raise ValueError(
            "Event manifest approved "
            f"{approval.approved_seat_environments} seat-environments but requires "
            f"{seat_environments}"
        )
    if approval.approved_retention_hours != manifest.retention.hours:
        raise ValueError(
            "Approved retention does not match the event retention policy"
        )

    capacity_shortfall = max(
        0, peak_retained_environments - supply.certified_capacity
    )
    eligible = capacity_shortfall == 0
    if eligible:
        explanation = (
            f"Certified execution capacity covers all {seat_environments} "
            "retained seat-environments."
        )
    else:
        explanation = (
            f"Certified execution capacity is short by {capacity_shortfall} "
            f"seat-environments. DR-reserved capacity ({supply.dr_reserved_capacity}) "
            f"and uncertified capacity ({supply.uncertified_capacity}) are visible but "
            "excluded from placement eligibility."
        )

    return EventCapacityPreview(
        participant_count=participant_count,
        seat_environments=seat_environments,
        peak_concurrent_participants=peak_concurrent_participants,
        peak_retained_environments=peak_retained_environments,
        certified_capacity=supply.certified_capacity,
        dr_reserved_capacity=supply.dr_reserved_capacity,
        uncertified_capacity=supply.uncertified_capacity,
        capacity_shortfall=capacity_shortfall,
        eligible=eligible,
        explanation=explanation,
    )
