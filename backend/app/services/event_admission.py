"""Join ACM fleet eligibility with Launchpad certification evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.acm import AcmPlacementSnapshot
from app.domain.events import EventCapacitySupply


class EventAdmissionUnavailableError(RuntimeError):
    """Fresh, trustworthy fleet admission evidence is unavailable."""


def apply_acm_eligibility(
    supply: EventCapacitySupply,
    snapshot: AcmPlacementSnapshot,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 120,
    max_future_skew_seconds: int = 30,
) -> EventCapacitySupply:
    """Intersect, never replace, matrix certification with ACM eligibility."""

    current = now or datetime.now(UTC)
    if current.tzinfo is None or snapshot.observed_at.tzinfo is None:
        raise EventAdmissionUnavailableError(
            "Fleet snapshot timestamps must include a timezone"
        )
    age_seconds = (current - snapshot.observed_at).total_seconds()
    if age_seconds > max_age_seconds:
        stale_by = int(age_seconds - max_age_seconds)
        raise EventAdmissionUnavailableError(
            f"Fleet snapshot is stale by {stale_by} second(s)"
        )
    if age_seconds < -max_future_skew_seconds:
        raise EventAdmissionUnavailableError("Fleet snapshot is future-dated")

    candidates = set(snapshot.eligible_cluster_ids)
    clusters = [
        cluster.model_copy(
            update={"enabled": cluster.enabled and cluster.cluster_id in candidates}
        )
        for cluster in supply.clusters
    ]
    return supply.model_copy(
        update={
            "fleet_snapshot_id": snapshot.snapshot_id,
            "fleet_observed_at": snapshot.observed_at,
            "clusters": clusters,
        }
    )
