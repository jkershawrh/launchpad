"""Materialized view refresh functions for Launchpad dashboard performance.

Pre-computes feedback summaries and session analytics so dashboard
endpoints read aggregated data instead of iterating all records.
"""
from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger("launchpad.views")


def refresh_feedback_summary(outcomes: list) -> List[Dict]:
    """Pre-compute feedback summary from provisioning outcomes.

    Groups outcomes by (catalog_item_id, cluster_name, hardware_profile)
    and computes success rate, avg duration, counts.

    This runs in-memory since Launchpad may be in mock mode without DB.
    """
    if not outcomes:
        return []

    groups = {}
    for o in outcomes:
        key = (
            getattr(o, "catalog_item_id", None) or o.get("catalog_item_id", ""),
            getattr(o, "cluster_name", None) or o.get("cluster_name", ""),
            getattr(o, "hardware_profile", None) or o.get("hardware_profile", ""),
        )
        groups.setdefault(key, []).append(o)

    summaries = []
    for (catalog, cluster, hw), items in groups.items():
        total = len(items)
        successes = sum(1 for i in items if (getattr(i, "success", None) or i.get("success", False)))
        durations = [
            getattr(i, "provisioning_duration_s", None) or i.get("provisioning_duration_s", 0)
            for i in items
            if (getattr(i, "provisioning_duration_s", None) or i.get("provisioning_duration_s", 0)) > 0
        ]
        summaries.append({
            "catalog_item_id": catalog,
            "cluster_name": cluster,
            "hardware_profile": hw,
            "total_outcomes": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": round(100.0 * successes / total, 1) if total > 0 else 0,
            "avg_duration_s": round(sum(durations) / len(durations), 1) if durations else None,
        })

    return sorted(summaries, key=lambda s: -s["total_outcomes"])


def refresh_session_analytics(sessions: list) -> Dict:
    """Pre-compute session analytics from current sessions.

    Groups sessions by status and catalog_item_id. Works in-memory
    since sessions may not be persisted (mock mode).
    """
    if not sessions:
        return {"by_status": {}, "by_catalog": {}, "total": 0}

    by_status = {}
    by_catalog = {}
    for s in sessions:
        status = getattr(s, "status", None)
        if hasattr(status, "value"):
            status = status.value
        elif isinstance(s, dict):
            status = s.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        catalog = getattr(s, "catalog_item_id", None) or (s.get("catalog_item_id", "") if isinstance(s, dict) else "")
        by_catalog[catalog] = by_catalog.get(catalog, 0) + 1

    return {
        "by_status": by_status,
        "by_catalog": by_catalog,
        "total": len(sessions),
    }
