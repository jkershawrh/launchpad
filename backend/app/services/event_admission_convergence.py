"""Read-only local rehearsal of independent event admission evidence gates.

This is intentionally not wired into the authoritative reservation API. It
requires trusted producers and transaction-safe capacity joining first.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.event_artifact_health import (
    ArtifactReadinessRequirement,
    EventArtifactHealthSnapshot,
)
from app.domain.event_inflight_capacity import (
    EventInflightCapacitySnapshot,
    InflightResourceVector,
)
from app.domain.event_model_health import EventModelHealthSnapshot
from app.domain.events import EventCapacityReservation, EventCapacitySupply, EventRecord
from app.services.event_artifact_health import assess_event_artifact_health
from app.services.event_artifact_requirements import (
    ArtifactRequirementSourceError,
    EligibleNodeSource,
    PromotedReleaseSource,
    build_event_artifact_requirements,
)
from app.services.event_inflight_capacity import assess_event_inflight_capacity
from app.services.event_model_health import assess_event_model_health
from app.services.event_reservations import (
    build_event_reservation_plan,
    forecast_event_admission,
)


@dataclass(frozen=True)
class EventAdmissionConvergenceAssessment:
    status: str
    explanation: str
    model_status: str
    artifact_status: str
    inflight_status: str
    reservation_count: int = 0
    evidence_ids: dict[str, str] = field(default_factory=dict)


def _evidence_ids(
    supply: EventCapacitySupply,
    model: EventModelHealthSnapshot | None,
    artifact: EventArtifactHealthSnapshot | None,
    inflight: EventInflightCapacitySnapshot | None,
) -> dict[str, str]:
    identifiers = {
        "capacity_matrix": supply.matrix_digest,
        "fleet": supply.fleet_snapshot_id,
    }
    for name, snapshot in (("model", model), ("artifact", artifact), ("inflight", inflight)):
        if snapshot is not None:
            identifiers[name] = snapshot.snapshot_id
    return identifiers


def assess_event_admission_with_sources(
    record: EventRecord,
    supply: EventCapacitySupply,
    active: list[EventCapacityReservation],
    releases: PromotedReleaseSource,
    nodes: EligibleNodeSource,
    artifact_snapshot: EventArtifactHealthSnapshot | None,
    inflight_snapshot: EventInflightCapacitySnapshot | None,
    *,
    now: datetime,
    model_health: EventModelHealthSnapshot | None = None,
) -> EventAdmissionConvergenceAssessment:
    """Future admission entry point: derive expectations from trusted sources."""

    if now.tzinfo is None:
        return EventAdmissionConvergenceAssessment(
            "blocked",
            "Admission time requires a timezone",
            "blocked",
            "not_evaluated",
            "not_evaluated",
            evidence_ids=_evidence_ids(supply, model_health, artifact_snapshot, inflight_snapshot),
        )
    try:
        requirements = build_event_artifact_requirements(record, releases, nodes, now=now)
    except ArtifactRequirementSourceError as exc:
        model = assess_event_model_health(record, model_health, now)
        return EventAdmissionConvergenceAssessment(
            "blocked",
            str(exc),
            model.status,
            "blocked",
            "not_evaluated",
            evidence_ids=_evidence_ids(supply, model_health, artifact_snapshot, inflight_snapshot),
        )
    return assess_event_admission_convergence(
        record,
        supply,
        active,
        requirements,
        artifact_snapshot,
        inflight_snapshot,
        now=now,
        model_health=model_health,
    )


def assess_event_admission_convergence(
    record: EventRecord,
    supply: EventCapacitySupply,
    active: list[EventCapacityReservation],
    artifact_requirements: list[ArtifactReadinessRequirement],
    artifact_snapshot: EventArtifactHealthSnapshot | None,
    inflight_snapshot: EventInflightCapacitySnapshot | None,
    *,
    now: datetime,
    model_health: EventModelHealthSnapshot | None = None,
) -> EventAdmissionConvergenceAssessment:
    """Join four local gates without creating or releasing a reservation."""

    if now.tzinfo is None:
        return EventAdmissionConvergenceAssessment(
            "blocked",
            "Admission time requires a timezone",
            "blocked",
            "not_evaluated",
            "not_evaluated",
            evidence_ids=_evidence_ids(supply, model_health, artifact_snapshot, inflight_snapshot),
        )
    model = assess_event_model_health(record, model_health, now)

    def blocked(reason: str, artifact="not_evaluated", inflight="not_evaluated"):
        return EventAdmissionConvergenceAssessment(
            "blocked",
            reason,
            model.status,
            artifact,
            inflight,
            evidence_ids=_evidence_ids(supply, model_health, artifact_snapshot, inflight_snapshot),
        )

    if any(item.event_id == record.manifest.event_id for item in active):
        return blocked("An existing event hold requires reconciliation, not a second candidate")

    forecast = forecast_event_admission(record, supply, active, now=now, model_health=model_health)
    if not forecast.eligible or forecast.status != "available":
        return blocked(forecast.explanation)

    expected = {
        (item.cluster_id, item.catalog_id, item.catalog_release)
        for item in record.capacity_preview.allocations
    }
    actual = [
        (item.cluster_id, item.catalog_id, item.catalog_release) for item in artifact_requirements
    ]
    if not expected or len(actual) != len(set(actual)) or set(actual) != expected:
        return blocked("Trusted artifact requirements do not exactly cover approved allocations")

    artifact = assess_event_artifact_health(artifact_requirements, artifact_snapshot, now)
    if artifact.status != "ready":
        return blocked(artifact.explanation, artifact=artifact.status)

    plan = build_event_reservation_plan(
        record,
        supply,
        expires_at=now + timedelta(minutes=5),
        now=now,
        model_health=model_health,
    )
    candidate: dict[str, InflightResourceVector] = {}
    for reservation in plan.reservations:
        current = candidate.setdefault(reservation.cluster_ref, InflightResourceVector())
        vector = reservation.resources
        candidate[reservation.cluster_ref] = InflightResourceVector(
            cpu_millicores=current.cpu_millicores + vector.cpu_millicores,
            memory_mib=current.memory_mib + vector.memory_mib,
            pods=current.pods + vector.pods,
            model_slots=current.model_slots + vector.model_slots,
        )
    inflight = assess_event_inflight_capacity(candidate, active, inflight_snapshot, now=now)
    if inflight.status != "available":
        return blocked(inflight.explanation, artifact="ready", inflight=inflight.status)
    return EventAdmissionConvergenceAssessment(
        "available",
        "All local event admission evidence gates pass",
        model.status,
        artifact.status,
        inflight.status,
        len(plan.reservations),
        _evidence_ids(supply, model_health, artifact_snapshot, inflight_snapshot),
    )
