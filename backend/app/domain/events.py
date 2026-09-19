from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_EVENT_WORKSHOPS = 100
MAX_ALLOCATION_STATES = 100_000


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
    placement_policy: Literal["single_cluster_per_workshop"]
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


class EventCatalogCapacity(BaseModel):
    """Certified simultaneous seat limit for one immutable catalog release."""

    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    certified_seats: int = Field(ge=0)


class EventClusterCapacity(BaseModel):
    """Server-owned event capacity envelope for one execution cluster."""

    cluster_id: str = Field(min_length=1)
    enabled: bool = False
    priority: int = Field(default=100, ge=0)
    exposure_policies: list[Literal["internal", "public_code"]] = Field(
        default_factory=list
    )
    capabilities: list[str] = Field(default_factory=list)
    certified_seats: int = Field(default=0, ge=0)
    dr_reserved_seats: int = Field(default=0, ge=0)
    uncertified_seats: int = Field(default=0, ge=0)
    catalogs: list[EventCatalogCapacity] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_catalog_releases(self) -> EventClusterCapacity:
        keys = [(item.catalog_id, item.catalog_release) for item in self.catalogs]
        if len(keys) != len(set(keys)):
            raise ValueError(
                f"Cluster {self.cluster_id} contains duplicate catalog release capacity"
            )
        return self


class EventCapacitySupply(BaseModel):
    """Server-owned catalog-by-cluster certification matrix.

    Only enabled cluster envelopes with an exact catalog release, compatible
    exposure policy, and all required capabilities can satisfy event demand.
    DR-reserved and uncertified capacity remain visible but never placeable.
    """

    matrix_id: str = Field(default="unconfigured", min_length=1)
    matrix_digest: str = Field(default="unconfigured", min_length=1)
    clusters: list[EventClusterCapacity] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_clusters(self) -> EventCapacitySupply:
        cluster_ids = [item.cluster_id for item in self.clusters]
        if len(cluster_ids) != len(set(cluster_ids)):
            raise ValueError("Event capacity cluster IDs must be unique")
        return self


class EventCapacityMatrixDocument(BaseModel):
    """Versioned certification evidence consumed by the server-side provider."""

    schema_version: Literal["launchpad.intel.com/event-capacity/v1"]
    matrix_id: str = Field(min_length=1)
    approved_by: list[str] = Field(min_length=2)
    approved_at: datetime
    evidence_refs: list[str] = Field(min_length=1)
    clusters: list[EventClusterCapacity] = Field(default_factory=list)

    @model_validator(mode="after")
    def approvals_are_distinct(self) -> EventCapacityMatrixDocument:
        if any(not item.strip() for item in self.approved_by):
            raise ValueError("capacity matrix approvers must be non-empty")
        if len(set(self.approved_by)) < 2:
            raise ValueError("capacity matrix requires two distinct approvers")
        if any(not item.strip() for item in self.evidence_refs):
            raise ValueError("capacity matrix evidence references must be non-empty")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("capacity matrix evidence references must be unique")
        if self.approved_at.tzinfo is None:
            raise ValueError("capacity matrix approval timestamp must include a timezone")
        return self

    def to_supply(self, matrix_digest: str) -> EventCapacitySupply:
        return EventCapacitySupply(
            matrix_id=self.matrix_id,
            matrix_digest=matrix_digest,
            clusters=self.clusters,
        )


class EventCapacityAllocation(BaseModel):
    cohort_id: str
    lab_ref: str
    catalog_id: str
    catalog_release: str
    cluster_id: str
    seats: int = Field(ge=1)


class EventLabCapacityDecision(BaseModel):
    lab_ref: str
    catalog_id: str
    catalog_release: str
    required_seats: int = Field(ge=1)
    allocated_seats: int = Field(ge=0)
    shortfall: int = Field(ge=0)


class EventCapacityPreview(BaseModel):
    matrix_id: str
    matrix_digest: str
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
    allocations: list[EventCapacityAllocation] = Field(default_factory=list)
    lab_capacity: list[EventLabCapacityDecision] = Field(default_factory=list)


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

    allocations, lab_capacity = _allocate_certified_capacity(manifest, supply)
    certified_capacity = sum(
        cluster.certified_seats
        for cluster in supply.clusters
        if cluster.enabled
        and manifest.exposure_policy in cluster.exposure_policies
    )
    dr_reserved_capacity = sum(
        cluster.dr_reserved_seats for cluster in supply.clusters
    )
    uncertified_capacity = sum(
        cluster.uncertified_seats for cluster in supply.clusters
    )
    capacity_shortfall = sum(item.shortfall for item in lab_capacity)
    eligible = capacity_shortfall == 0
    if eligible:
        explanation = (
            "The catalog-by-cluster certification matrix covers all "
            f"{seat_environments} retained seat-environments."
        )
    else:
        gaps = ", ".join(
            f"{item.lab_ref}: {item.shortfall}"
            for item in lab_capacity
            if item.shortfall
        )
        explanation = (
            f"Certified catalog-by-cluster capacity is short by {capacity_shortfall} "
            f"seat-environments ({gaps}). DR-reserved capacity "
            f"({dr_reserved_capacity}) and uncertified capacity "
            f"({uncertified_capacity}) are visible but excluded from placement "
            "eligibility."
        )

    return EventCapacityPreview(
        matrix_id=supply.matrix_id,
        matrix_digest=supply.matrix_digest,
        participant_count=participant_count,
        seat_environments=seat_environments,
        peak_concurrent_participants=peak_concurrent_participants,
        peak_retained_environments=peak_retained_environments,
        certified_capacity=certified_capacity,
        dr_reserved_capacity=dr_reserved_capacity,
        uncertified_capacity=uncertified_capacity,
        capacity_shortfall=capacity_shortfall,
        eligible=eligible,
        explanation=explanation,
        allocations=allocations,
        lab_capacity=lab_capacity,
    )


def _allocate_certified_capacity(
    manifest: EventManifest,
    supply: EventCapacitySupply,
) -> tuple[list[EventCapacityAllocation], list[EventLabCapacityDecision]]:
    """Place each cohort/lab workshop atomically within certified limits."""

    labs_by_ref = {lab.lab_ref: lab for lab in manifest.labs}
    workshops = [
        (cohort.cohort_id, labs_by_ref[lab_ref], cohort.participants)
        for cohort in manifest.cohorts
        for lab_ref in cohort.lab_refs
    ]
    if len(workshops) > MAX_EVENT_WORKSHOPS:
        raise ValueError(
            f"Event contains {len(workshops)} atomic workshops; maximum is "
            f"{MAX_EVENT_WORKSHOPS}"
        )
    clusters = [
        cluster
        for cluster in sorted(
            supply.clusters, key=lambda item: (item.priority, item.cluster_id)
        )
        if cluster.enabled
        and manifest.exposure_policy in cluster.exposure_policies
    ]
    catalog_limits = {
        (cluster.cluster_id, item.catalog_id, item.catalog_release): item.certified_seats
        for cluster in clusters
        for item in cluster.catalogs
    }

    def candidates(lab: EventLab) -> list[str]:
        return [
            cluster.cluster_id
            for cluster in clusters
            if set(lab.required_capabilities).issubset(cluster.capabilities)
            and (
                cluster.cluster_id,
                lab.catalog_id,
                lab.catalog_release,
            )
            in catalog_limits
        ]

    workshops.sort(
        key=lambda item: (
            len(candidates(item[1])),
            -item[2],
            item[0],
            item[1].lab_ref,
        )
    )
    cluster_remaining = {
        cluster.cluster_id: cluster.certified_seats for cluster in clusters
    }
    catalog_remaining = dict(catalog_limits)
    best: list[tuple[str, EventLab, int, str]] = []
    current: list[tuple[str, EventLab, int, str]] = []
    states = 0

    def search(index: int, allocated_seats: int) -> bool:
        nonlocal best, states
        states += 1
        if states > MAX_ALLOCATION_STATES:
            raise ValueError(
                "Event capacity allocation exceeded its bounded search budget"
            )
        if allocated_seats > sum(item[2] for item in best):
            best = list(current)
        if index == len(workshops):
            return len(current) == len(workshops)
        remaining_seats = sum(item[2] for item in workshops[index:])
        if allocated_seats + remaining_seats <= sum(item[2] for item in best):
            return False

        cohort_id, lab, seats = workshops[index]
        key_suffix = (lab.catalog_id, lab.catalog_release)
        for cluster_id in candidates(lab):
            cell = (cluster_id, *key_suffix)
            if cluster_remaining[cluster_id] < seats:
                continue
            if catalog_remaining[cell] < seats:
                continue
            cluster_remaining[cluster_id] -= seats
            catalog_remaining[cell] -= seats
            current.append((cohort_id, lab, seats, cluster_id))
            if search(index + 1, allocated_seats + seats):
                return True
            current.pop()
            catalog_remaining[cell] += seats
            cluster_remaining[cluster_id] += seats
        search(index + 1, allocated_seats)
        return False

    search(0, 0)
    allocations = [
        EventCapacityAllocation(
            cohort_id=cohort_id,
            lab_ref=lab.lab_ref,
            catalog_id=lab.catalog_id,
            catalog_release=lab.catalog_release,
            cluster_id=cluster_id,
            seats=seats,
        )
        for cohort_id, lab, seats, cluster_id in best
    ]
    allocations.sort(
        key=lambda item: (item.cohort_id, item.lab_ref, item.cluster_id)
    )
    lab_demand = {
        lab.lab_ref: sum(
            cohort.participants
            for cohort in manifest.cohorts
            if lab.lab_ref in cohort.lab_refs
        )
        for lab in manifest.labs
    }
    labs = sorted(
        (lab for lab in manifest.labs if lab_demand[lab.lab_ref] > 0),
        key=lambda item: item.lab_ref,
    )
    allocated_by_lab = {lab.lab_ref: 0 for lab in labs}
    for allocation in allocations:
        allocated_by_lab[allocation.lab_ref] += allocation.seats
    lab_capacity = [
        EventLabCapacityDecision(
            lab_ref=lab.lab_ref,
            catalog_id=lab.catalog_id,
            catalog_release=lab.catalog_release,
            required_seats=lab_demand[lab.lab_ref],
            allocated_seats=allocated_by_lab[lab.lab_ref],
            shortfall=lab_demand[lab.lab_ref] - allocated_by_lab[lab.lab_ref],
        )
        for lab in labs
    ]
    return allocations, lab_capacity
