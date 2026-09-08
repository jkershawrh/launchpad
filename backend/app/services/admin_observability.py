"""Read-only operator view joining cluster, lab, workshop and seat lifecycle data.

Launchpad owns workflow state, so this read model intentionally stays separate
from Prometheus/Grafana telemetry.  The UI uses it to answer "what is happening
to this order/seat?" and links to Grafana for historical resource and network
trends.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from math import ceil
from typing import Any

from app.domain.models import LabSession, Workshop

INFLIGHT_STATUSES = {
    "requested",
    "pending",
    "queued",
    "provisioning",
    "validating",
    "resetting",
    "reclaiming",
}
ACTIVE_STATUSES = {"ready", "active"}
ATTENTION_STATUSES = {"failed", "validation_failed", "cleanup_failed"}
RESOLVED_STATUSES = {"reclaimed"}


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _seconds(start: datetime | None, end: datetime | None) -> int | None:
    if not start or not end:
        return None
    return max(0, round((end - start).total_seconds()))


def _session_started(session: LabSession) -> datetime | None:
    if session.started_at:
        return session.started_at
    if session.lifecycle_events:
        return session.lifecycle_events[0].timestamp
    return None


def _last_transition(session: LabSession) -> datetime | None:
    if session.lifecycle_events:
        return session.lifecycle_events[-1].timestamp
    return session.completed_at or session.started_at


def _ready_at(session: LabSession) -> datetime | None:
    for event in session.lifecycle_events:
        if _value(event.to_status) in ACTIVE_STATUSES:
            return event.timestamp
    if _value(session.status) in ACTIVE_STATUSES:
        return _last_transition(session)
    return None


def _resolution_state(status: str) -> str:
    if status in ATTENTION_STATUSES:
        return "attention"
    if status in {"resetting", "reclaiming"}:
        return "resolving"
    if status in RESOLVED_STATUSES:
        return "resolved"
    return "none"


def _session_error(session: LabSession) -> str | None:
    failed_validation = next(
        (
            result.message
            for result in reversed(session.validation_results)
            if _value(result.result) == "fail" and result.message
        ),
        None,
    )
    if failed_validation:
        return failed_validation
    if _value(session.status) in ATTENTION_STATUSES and session.lifecycle_events:
        return session.lifecycle_events[-1].reason
    return None


def _seat_row(
    *,
    session: LabSession | None,
    seat_number: int,
    fallback_status: str,
    fallback_error: str | None,
    now: datetime,
) -> dict[str, Any]:
    status = _value(session.status) if session else fallback_status
    started_at = _session_started(session) if session else None
    last_transition_at = _last_transition(session) if session else None
    ready_at = _ready_at(session) if session else None
    end = ready_at or last_transition_at or now
    return {
        "seat_number": seat_number,
        "session_id": session.session_id if session else None,
        "namespace": session.namespace if session else None,
        "status": status,
        "started_at": _iso(started_at),
        "last_transition_at": _iso(last_transition_at),
        "provisioning_seconds": _seconds(started_at, end),
        "resolution_state": _resolution_state(status),
        "error": fallback_error or (_session_error(session) if session else None),
        "detail_url": f"/sessions/{session.session_id}" if session else None,
    }


def _lab_row(
    *,
    order_id: str,
    order_type: str,
    name: str,
    catalog_item_id: str,
    cluster_ref: str | None,
    status: str,
    started_at: datetime | None,
    seats: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    counts = dict(sorted(Counter(seat["status"] for seat in seats).items()))
    inflight = [seat for seat in seats if seat["status"] in INFLIGHT_STATUSES]
    ready_durations = [
        seat["provisioning_seconds"]
        for seat in seats
        if seat["status"] in ACTIVE_STATUSES
        and seat["provisioning_seconds"] is not None
    ]
    oldest_started = min(
        (
            datetime.fromisoformat(seat["started_at"])
            for seat in inflight
            if seat["started_at"]
        ),
        default=None,
    )
    if inflight and oldest_started is None:
        oldest_started = started_at
    failed_count = sum(counts.get(value, 0) for value in ATTENTION_STATUSES)
    return {
        "order_id": order_id,
        "order_type": order_type,
        "name": name,
        "catalog_item_id": catalog_item_id,
        "cluster_ref": cluster_ref,
        "status": status,
        "started_at": _iso(started_at),
        "seats_requested": len(seats),
        "ready_seats": sum(counts.get(value, 0) for value in ACTIVE_STATUSES),
        "failed_seats": failed_count,
        "inflight_seats": len(inflight),
        "status_counts": counts,
        "max_ready_seconds": max(ready_durations) if ready_durations else None,
        "oldest_inflight_seconds": _seconds(oldest_started, now),
        "seats": seats,
        "detail_url": (
            f"/workshops/{order_id}"
            if order_type == "workshop"
            else seats[0]["detail_url"] if seats else None
        ),
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 1)


def _llm_observability(
    *,
    model_inventory: Mapping[str, Any],
    llm_events: list[dict[str, Any]],
    labs: list[dict[str, Any]],
) -> dict[str, Any]:
    inventory_summary = model_inventory.get("summary", {}) or {}
    models = []
    for item in model_inventory.get("models", []) or []:
        namespace = item.get("namespace")
        workload = item.get("workload")
        exposed = bool(item.get("litellm_exposed"))
        models.append(
            {
                "model_id": item.get("id"),
                "display_name": item.get("display_name") or item.get("id"),
                "hardware": item.get("hardware"),
                "status": item.get("status", "unknown"),
                "desired_replicas": int(item.get("desired_replicas", 0) or 0),
                "ready_replicas": int(item.get("ready_replicas", 0) or 0),
                "route": (
                    f"LiteLLM: {item.get('id')}"
                    if exposed
                    else "Not exposed through LiteLLM"
                ),
                "backend": (
                    f"{namespace}/{workload}"
                    if namespace and workload
                    else namespace or workload
                ),
            }
        )

    seat_lookup = []
    for lab in labs:
        for seat in lab["seats"]:
            if not seat["session_id"]:
                continue
            seat_lookup.append(
                {
                    "order_id": lab["order_id"],
                    "order_type": lab["order_type"],
                    "catalog_item_id": lab["catalog_item_id"],
                    "cluster_ref": lab["cluster_ref"],
                    "seat_number": seat["seat_number"],
                    "session_id": seat["session_id"],
                    "namespace": seat["namespace"],
                }
            )

    attribution_groups: dict[tuple[str, str], dict[str, Any]] = {}
    attributed_requests = 0
    for event in llm_events:
        caller = str(event.get("caller") or "")
        seat = next(
            (
                candidate
                for candidate in seat_lookup
                if candidate["session_id"] in caller
                or (
                    candidate["namespace"]
                    and str(candidate["namespace"]) in caller
                )
            ),
            None,
        )
        if not seat:
            continue
        attributed_requests += 1
        model_id = str(event.get("model") or "unknown")
        key = (seat["session_id"], model_id)
        group = attribution_groups.setdefault(
            key,
            {
                **seat,
                "model_id": model_id,
                "requests": 0,
                "latencies": [],
                "errors": 0,
                "rate_limited": 0,
                "estimated_tokens": 0,
            },
        )
        outcome = str(event.get("outcome") or "success")
        status_code = int(event.get("status_code", 200) or 200)
        group["requests"] += 1
        group["latencies"].append(float(event.get("latency_ms", 0) or 0))
        group["estimated_tokens"] += int(event.get("tokens_in_est", 0) or 0)
        group["estimated_tokens"] += int(event.get("tokens_out_est", 0) or 0)
        if outcome != "success" or status_code >= 400:
            group["errors"] += 1
        if outcome == "rate_limited" or status_code == 429:
            group["rate_limited"] += 1

    attribution = []
    for group in attribution_groups.values():
        latencies = group.pop("latencies")
        group["avg_latency_ms"] = (
            round(sum(latencies) / len(latencies), 1) if latencies else None
        )
        attribution.append(group)
    attribution.sort(
        key=lambda item: (item["order_id"], item["seat_number"], item["model_id"])
    )

    latencies = [float(event.get("latency_ms", 0) or 0) for event in llm_events]
    errors = sum(
        1
        for event in llm_events
        if str(event.get("outcome") or "success") != "success"
        or int(event.get("status_code", 200) or 200) >= 400
    )
    rate_limited = sum(
        1
        for event in llm_events
        if str(event.get("outcome") or "") == "rate_limited"
        or int(event.get("status_code", 200) or 200) == 429
    )
    gaps = []
    if not models:
        gaps.append("LLM endpoint/model inventory is unavailable")
    if not llm_events:
        gaps.append("No LLM request telemetry is currently available")
    elif any("outcome" not in event and "status_code" not in event for event in llm_events):
        gaps.append("LLM audit events do not yet record errors or rate-limit outcomes")
    if llm_events and attributed_requests < len(llm_events):
        gaps.append("Some LLM requests lack lab, workshop, and seat attribution")

    return {
        "summary": {
            "models_configured": int(inventory_summary.get("configured", len(models)) or 0),
            "models_running": int(inventory_summary.get("running", 0) or 0),
            "models_healthy": int(inventory_summary.get("healthy", 0) or 0),
            "requests_observed": len(llm_events),
            "avg_latency_ms": (
                round(sum(latencies) / len(latencies), 1) if latencies else None
            ),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "errors": errors,
            "rate_limited": rate_limited,
            "estimated_tokens": sum(
                int(event.get("tokens_in_est", 0) or 0)
                + int(event.get("tokens_out_est", 0) or 0)
                for event in llm_events
            ),
            "attributed_requests": attributed_requests,
        },
        "models": models,
        "attribution": attribution,
        "telemetry_gaps": gaps,
    }


def build_admin_observability(
    *,
    sessions: Iterable[LabSession],
    workshops: Iterable[Workshop],
    clusters: list[dict[str, Any]],
    now: datetime | None = None,
    grafana_url: str = "",
    catalog_names: Mapping[str, str] | None = None,
    model_inventory: Mapping[str, Any] | None = None,
    llm_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the versioned CDD response without mutating platform state."""

    # Domain records are currently persisted as naive UTC timestamps.
    now = now or datetime.now(UTC).replace(tzinfo=None)
    catalog_names = catalog_names or {}
    session_by_id = {session.session_id: session for session in sessions}
    claimed_session_ids: set[str] = set()
    labs: list[dict[str, Any]] = []

    for workshop in workshops:
        seats = []
        seat_started_at = []
        for seat in sorted(workshop.seats, key=lambda item: item.seat_number):
            session = session_by_id.get(seat.session_id) if seat.session_id else None
            if session:
                claimed_session_ids.add(session.session_id)
                if started_at := _session_started(session):
                    seat_started_at.append(started_at)
            seats.append(
                _seat_row(
                    session=session,
                    seat_number=seat.seat_number,
                    fallback_status=_value(seat.status),
                    fallback_error=seat.error,
                    now=now,
                )
            )
        labs.append(
            _lab_row(
                order_id=workshop.workshop_id,
                order_type="workshop",
                name=(
                    workshop.name
                    or catalog_names.get(workshop.catalog_item_id)
                    or workshop.catalog_item_id
                ),
                catalog_item_id=workshop.catalog_item_id,
                cluster_ref=workshop.cluster_ref or workshop.target_cluster,
                status=_value(workshop.status),
                started_at=(
                    workshop.started_at
                    or (min(seat_started_at) if seat_started_at else None)
                    or workshop.created_at
                ),
                seats=seats,
                now=now,
            )
        )

    for session in session_by_id.values():
        if session.session_id in claimed_session_ids:
            continue
        seat = _seat_row(
            session=session,
            seat_number=1,
            fallback_status=_value(session.status),
            fallback_error=None,
            now=now,
        )
        labs.append(
            _lab_row(
                order_id=session.session_id,
                order_type="individual",
                name=(
                    catalog_names.get(session.catalog_item_id)
                    or session.catalog_item_id
                ),
                catalog_item_id=session.catalog_item_id,
                cluster_ref=session.cluster_ref,
                status=_value(session.status),
                started_at=_session_started(session),
                seats=[seat],
                now=now,
            )
        )

    labs.sort(key=lambda lab: lab["started_at"] or "", reverse=True)
    inflight = [
        {
            "order_id": lab["order_id"],
            "order_type": lab["order_type"],
            "name": lab["name"],
            "catalog_item_id": lab["catalog_item_id"],
            "cluster_ref": lab["cluster_ref"],
            "inflight_seats": lab["inflight_seats"],
            "stage_counts": {
                status: count
                for status, count in lab["status_counts"].items()
                if status in INFLIGHT_STATUSES
            },
            "oldest_seconds": lab["oldest_inflight_seconds"],
            "detail_url": lab["detail_url"],
        }
        for lab in labs
        if lab["inflight_seats"]
    ]
    resolution = []
    for lab in labs:
        for seat in lab["seats"]:
            if seat["resolution_state"] == "none":
                continue
            resolution.append(
                {
                    "order_id": lab["order_id"],
                    "order_type": lab["order_type"],
                    "name": lab["name"],
                    "catalog_item_id": lab["catalog_item_id"],
                    "cluster_ref": lab["cluster_ref"],
                    "seat_number": seat["seat_number"],
                    "session_id": seat["session_id"],
                    "status": seat["status"],
                    "state": seat["resolution_state"],
                    "message": seat["error"],
                    "last_transition_at": seat["last_transition_at"],
                    "detail_url": seat["detail_url"] or lab["detail_url"],
                }
            )

    active_labs = [
        lab
        for lab in labs
        if lab["status"]
        not in {"completed", "completed_with_errors", "failed", "reclaimed"}
    ]
    seats = [seat for lab in labs for seat in lab["seats"]]
    healthy_clusters = sum(
        1 for cluster in clusters if cluster.get("healthy") is True
    )
    clean_grafana_url = grafana_url.strip() or None
    return {
        "schema": "launchpad.admin-observability/v1",
        "generated_at": now.isoformat(),
        "summary": {
            "clusters_healthy": healthy_clusters,
            "clusters_total": len(clusters),
            "labs_active": len(active_labs),
            "seats_active": sum(
                1 for seat in seats if seat["status"] in ACTIVE_STATUSES
            ),
            "seats_inflight": sum(
                1 for seat in seats if seat["status"] in INFLIGHT_STATUSES
            ),
            "seats_attention": sum(
                1 for seat in seats if seat["status"] in ATTENTION_STATUSES
            ),
        },
        "clusters": clusters,
        "provisioning": labs,
        "inflight": inflight,
        "resolution": resolution,
        "grafana": {
            "configured": bool(clean_grafana_url),
            "url": clean_grafana_url,
            "purpose": "Historical resource, network, and latency telemetry",
        },
        "llm": _llm_observability(
            model_inventory=model_inventory or {},
            llm_events=llm_events or [],
            labs=labs,
        ),
    }
