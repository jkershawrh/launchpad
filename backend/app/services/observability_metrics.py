"""Prometheus exposition for Launchpad-owned lifecycle state.

The exporter deliberately uses only bounded operational labels. Tenant,
participant, requester, namespace, workshop, seat, email, route and credential
values are not Prometheus labels. Exact order and seat drill-down belongs in
the authenticated admin read model; Prometheus retains aggregate trends.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from math import isfinite

from app.domain.lifecycle_jobs import LifecycleJob
from app.domain.models import LabSession, Workshop

INFLIGHT_SESSION_STATES = {"requested", "provisioning", "validating", "resetting"}
ACTIVE_SESSION_STATES = {"ready", "active"}
INFLIGHT_WORKSHOP_STATES = {
    "capacity_checking",
    "queued",
    "provisioning",
    "partially_ready",
    "reclaiming",
}


METRICS = {
    "launchpad_sessions": ("gauge", "Sessions grouped by bounded operational dimensions."),
    "launchpad_workshops": ("gauge", "Workshop orders grouped by state."),
    "launchpad_workshop_seats": ("gauge", "Seats in a workshop grouped by state."),
    "launchpad_session_state": ("gauge", "Sessions grouped by current state."),
    "launchpad_session_state_age_seconds_max": (
        "gauge",
        "Maximum seconds since a lifecycle transition for the group.",
    ),
    "launchpad_session_inflight": (
        "gauge",
        "One when a session is in a provisioning or reclaim operation.",
    ),
    "launchpad_session_provision_duration_seconds_sum": (
        "gauge",
        "Sum of observed provision-to-ready-or-failure durations.",
    ),
    "launchpad_session_provision_duration_seconds_count": (
        "gauge",
        "Count of observed provision-to-ready-or-failure durations.",
    ),
    "launchpad_session_provision_duration_seconds_max": (
        "gauge",
        "Maximum observed provision-to-ready-or-failure duration.",
    ),
    "launchpad_session_resolution_duration_seconds_sum": (
        "gauge",
        "Sum of observed resetting-to-resolution durations.",
    ),
    "launchpad_session_resolution_duration_seconds_count": (
        "gauge",
        "Count of observed resetting-to-resolution durations.",
    ),
    "launchpad_session_resolution_duration_seconds_max": (
        "gauge",
        "Maximum observed resetting-to-resolution duration.",
    ),
    "launchpad_session_validation_failures": (
        "gauge",
        "Failed validation checks recorded for a session.",
    ),
    "launchpad_session_transitions_total": (
        "counter",
        "Persisted lifecycle transitions, aggregated without identity labels.",
    ),
    "launchpad_cluster_active_sessions": (
        "gauge",
        "Active or in-flight sessions assigned to a cluster.",
    ),
    "launchpad_cluster_active_workshops": (
        "gauge",
        "Active or in-flight workshops assigned to a cluster.",
    ),
    "launchpad_cluster_active_seats": (
        "gauge",
        "Active or in-flight workshop seats assigned to a cluster.",
    ),
    "launchpad_cluster_target_info": ("gauge", "Configured execution target metadata."),
    "launchpad_cluster_placement_enabled": (
        "gauge",
        "One when normal placement is enabled for the target.",
    ),
    "launchpad_cluster_model_configured_info": (
        "gauge",
        "Configured model availability; this is not a live readiness signal.",
    ),
    "launchpad_lifecycle_jobs": (
        "gauge",
        "Durable lifecycle jobs grouped by bounded operational dimensions.",
    ),
    "launchpad_lifecycle_job_age_seconds_max": (
        "gauge",
        "Maximum age of a lifecycle job in its current operational group.",
    ),
    "launchpad_lifecycle_lease_seconds_remaining": (
        "gauge",
        "Seconds remaining on active lifecycle ownership leases.",
    ),
    "launchpad_lifecycle_takeovers_total": (
        "counter",
        "Lease takeovers after the first lifecycle execution attempt.",
    ),
}


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _label_text(labels: dict[str, object]) -> str:
    if not labels:
        return ""
    values = ",".join(f'{name}="{_escape(value)}"' for name, value in sorted(labels.items()))
    return "{" + values + "}"


def _event_time(session: LabSession, states: set[str], *, last: bool = False) -> datetime | None:
    matches = [
        event.timestamp for event in session.lifecycle_events if _value(event.to_status) in states
    ]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _seconds_between(later: datetime, earlier: datetime) -> float:
    return (_utc(later) - _utc(earlier)).total_seconds()


def render_launchpad_metrics(
    *,
    sessions: Iterable[LabSession],
    workshops: Iterable[Workshop],
    cluster_targets: Iterable[object],
    lifecycle_jobs: Iterable[LifecycleJob] = (),
    now: datetime | None = None,
) -> bytes:
    """Render a deterministic Prometheus text snapshot.

    The state is reconstructed from persisted Launchpad records on every
    scrape.  This survives backend restarts and avoids a second metrics-only
    source of truth.
    """

    now = now or datetime.now(UTC).replace(tzinfo=None)
    session_list = list(sessions)
    workshop_list = list(workshops)
    samples: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)

    def add(name: str, labels: dict[str, object], value: float = 1, *, mode: str = "sum") -> None:
        numeric = float(value)
        if not isfinite(numeric):
            return
        key = (name, tuple(sorted((label, str(item)) for label, item in labels.items())))
        if mode == "max":
            samples[key] = max(samples.get(key, numeric), numeric)
        else:
            samples[key] += numeric

    active_session_counts: dict[str, int] = defaultdict(int)
    active_workshop_counts: dict[str, int] = defaultdict(int)
    active_seat_counts: dict[str, int] = defaultdict(int)

    for session in session_list:
        cluster = session.cluster_ref or "unassigned"
        status = _value(session.status)
        base = {
            "cluster": cluster,
            "catalog_item": session.catalog_item_id,
        }
        add(
            "launchpad_sessions",
            {"cluster": cluster, "catalog_item": session.catalog_item_id, "status": status},
        )
        add("launchpad_session_state", {**base, "status": status})

        latest = session.lifecycle_events[-1].timestamp if session.lifecycle_events else None
        if latest:
            add(
                "launchpad_session_state_age_seconds_max",
                {**base, "status": status},
                max(0, (now - latest).total_seconds()),
                mode="max",
            )
        inflight = status in INFLIGHT_SESSION_STATES
        add("launchpad_session_inflight", {**base, "status": status}, int(inflight))
        if status in INFLIGHT_SESSION_STATES | ACTIVE_SESSION_STATES:
            active_session_counts[cluster] += 1

        provision_start = _event_time(session, {"provisioning"})
        provision_end = _event_time(
            session,
            {"ready", "validation_failed", "failed", "rejected"},
        )
        if provision_start and provision_end and provision_end >= provision_start:
            outcome = _value(
                next(
                    event.to_status
                    for event in session.lifecycle_events
                    if event.timestamp == provision_end
                )
            )
            add(
                "launchpad_session_provision_duration_seconds_sum",
                {**base, "outcome": outcome},
                (provision_end - provision_start).total_seconds(),
            )
            add(
                "launchpad_session_provision_duration_seconds_count",
                {**base, "outcome": outcome},
            )
            add(
                "launchpad_session_provision_duration_seconds_max",
                {**base, "outcome": outcome},
                (provision_end - provision_start).total_seconds(),
                mode="max",
            )

        resolution_start = _event_time(session, {"resetting"}, last=True)
        resolution_end = _event_time(session, {"reclaimed", "cleanup_failed"}, last=True)
        if resolution_start and resolution_end and resolution_end >= resolution_start:
            outcome = _value(
                next(
                    event.to_status
                    for event in reversed(session.lifecycle_events)
                    if event.timestamp == resolution_end
                )
            )
            add(
                "launchpad_session_resolution_duration_seconds_sum",
                {**base, "outcome": outcome},
                (resolution_end - resolution_start).total_seconds(),
            )
            add(
                "launchpad_session_resolution_duration_seconds_count",
                {**base, "outcome": outcome},
            )
            add(
                "launchpad_session_resolution_duration_seconds_max",
                {**base, "outcome": outcome},
                (resolution_end - resolution_start).total_seconds(),
                mode="max",
            )

        validation_failures = sum(
            1 for result in session.validation_results if _value(result.result) == "fail"
        )
        add(
            "launchpad_session_validation_failures",
            base,
            validation_failures,
        )
        for event in session.lifecycle_events:
            add(
                "launchpad_session_transitions_total",
                {
                    "cluster": cluster,
                    "catalog_item": session.catalog_item_id,
                    "from_status": _value(event.from_status),
                    "to_status": _value(event.to_status),
                },
            )

    for workshop in workshop_list:
        cluster = workshop.cluster_ref or workshop.target_cluster or "unassigned"
        status = _value(workshop.status)
        add(
            "launchpad_workshops",
            {
                "cluster": cluster,
                "catalog_item": workshop.catalog_item_id,
                "exposure": _value(workshop.exposure_policy),
                "status": status,
            },
        )
        if status in INFLIGHT_WORKSHOP_STATES | ACTIVE_SESSION_STATES:
            active_workshop_counts[cluster] += 1
        for seat in workshop.seats:
            seat_status = _value(seat.status)
            add(
                "launchpad_workshop_seats",
                {
                    "cluster": cluster,
                    "catalog_item": workshop.catalog_item_id,
                    "status": seat_status,
                },
            )
            if seat_status in INFLIGHT_SESSION_STATES | ACTIVE_SESSION_STATES:
                active_seat_counts[cluster] += 1

    targets = list(cluster_targets)
    for target in targets:
        cluster = str(getattr(target, "cluster_id", "unknown"))
        enabled = bool(getattr(target, "enabled", False))
        add(
            "launchpad_cluster_target_info",
            {
                "cluster": cluster,
                "display_name": getattr(target, "display_name", cluster),
            },
            1,
            mode="max",
        )
        add("launchpad_cluster_placement_enabled", {"cluster": cluster}, int(enabled), mode="max")
        for model in sorted((getattr(target, "model_endpoints", {}) or {}).keys()):
            add(
                "launchpad_cluster_model_configured_info",
                {"cluster": cluster, "model": model},
                1,
                mode="max",
            )

    for job in lifecycle_jobs:
        cluster = job.cluster_ref or "unassigned"
        operation = _value(job.operation)
        status = _value(job.status)
        labels = {"cluster": cluster, "operation": operation, "status": status}
        add("launchpad_lifecycle_jobs", labels)
        add(
            "launchpad_lifecycle_job_age_seconds_max",
            labels,
            max(0, _seconds_between(now, job.updated_at)),
            mode="max",
        )
        if job.lease_until is not None and status in {"running", "cancel_requested"}:
            add(
                "launchpad_lifecycle_lease_seconds_remaining",
                {"cluster": cluster, "operation": operation},
                max(0, _seconds_between(job.lease_until, now)),
                mode="max",
            )
        add(
            "launchpad_lifecycle_takeovers_total",
            {"cluster": cluster, "operation": operation},
            max(0, job.attempts - 1),
        )

    clusters = {
        *active_session_counts,
        *active_workshop_counts,
        *active_seat_counts,
        *(str(getattr(target, "cluster_id", "unknown")) for target in targets),
    }
    for cluster in clusters:
        add(
            "launchpad_cluster_active_sessions",
            {"cluster": cluster},
            active_session_counts[cluster],
            mode="max",
        )
        add(
            "launchpad_cluster_active_workshops",
            {"cluster": cluster},
            active_workshop_counts[cluster],
            mode="max",
        )
        add(
            "launchpad_cluster_active_seats",
            {"cluster": cluster},
            active_seat_counts[cluster],
            mode="max",
        )

    lines: list[str] = []
    for name, (metric_type, help_text) in METRICS.items():
        lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} {metric_type}"))
        matching = sorted(
            (labels, value)
            for (sample_name, labels), value in samples.items()
            if sample_name == name
        )
        for labels, value in matching:
            rendered_value = str(int(value)) if value.is_integer() else str(round(value, 6))
            lines.append(f"{name}{_label_text(dict(labels))} {rendered_value}")
    return ("\n".join(lines) + "\n").encode()
