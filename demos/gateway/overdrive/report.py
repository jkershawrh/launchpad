"""Build and route reports for Overdrive."""

from collections import Counter
from .models import Decision


def build_report(test_results: dict) -> dict:
    stages = []
    blocking = []
    for name, results in test_results.items():
        status = "green" if results["failures"] == 0 else "red"
        stages.append({
            "name": name,
            "status": status,
            "tests": results["tests"],
            "failures": results["failures"],
        })
        if status == "red":
            blocking.append(name)
    return {
        "build_status": "green" if not blocking else "red",
        "stages": stages,
        "blocking": blocking,
    }


def route_report(batch_id: str, decisions: list) -> dict:
    if not decisions:
        return {"batch_id": batch_id, "total_requests": 0, "routes": {}, "fallbacks": 0, "indeterminate": 0, "top_reason_codes": []}

    route_counts = Counter()
    fallbacks = 0
    indeterminate = 0
    all_reasons = Counter()

    for d in decisions:
        if d.outcome == "route" and d.selected_route:
            route_counts[d.selected_route] += 1
        elif d.outcome == "fallback" and d.selected_route:
            route_counts[d.selected_route] += 1
            fallbacks += 1
        elif d.outcome in ("indeterminate", "queue"):
            indeterminate += 1
        for rc in d.reason_codes:
            all_reasons[rc] += 1

    return {
        "batch_id": batch_id,
        "total_requests": len(decisions),
        "routes": dict(route_counts),
        "fallbacks": fallbacks,
        "indeterminate": indeterminate,
        "top_reason_codes": [rc for rc, _ in all_reasons.most_common(5)],
    }
