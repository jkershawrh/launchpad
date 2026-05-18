"""Replay Comparison — run same workload with different hardware configs."""

import random

from .workload_generator import generate_workload
from .engine import OverdriveEngine
from .timing_provider import MockTimingProvider
from .metrics_collector import collect_metrics
from pathlib import Path

_CONFIG = Path(__file__).parent / "config.yaml"
_RUBRICS = Path(__file__).parents[2] / "tests" / "rubrics" / "routes"

XEON_ONLY_LATENCY = {"eco": 120, "performance": 250, "overdrive": 800}
XEON_GAUDI_LATENCY = {"eco": 80, "performance": 150, "overdrive": 200}


def run_comparison(profile: str = "incident_storm", seed: int = 42) -> dict:
    requests = generate_workload(profile=profile, mode="drive", seed=seed)
    engine = OverdriveEngine(config_path=_CONFIG, rubric_dir=_RUBRICS)
    rng = random.Random(seed)

    run_a_results = []
    run_b_results = []

    for req in requests:
        decision = engine.evaluate(req)
        lane = decision.selected_route or "performance"
        expected_output = max(50, req.token_estimate // 10)

        lat_a = round(XEON_ONLY_LATENCY.get(lane, 400) * (1 + req.token_estimate / 10000) * rng.uniform(0.8, 1.3), 1)
        run_a_results.append({"lane": "performance", "latency_ms": lat_a, "input_tokens": req.token_estimate, "output_tokens": expected_output, "modality": req.modality, "image_count": req.image_count, "page_count": req.page_count})

        lat_b = round(XEON_GAUDI_LATENCY.get(lane, 200) * (1 + req.token_estimate / 10000) * rng.uniform(0.8, 1.3), 1)
        run_b_results.append({"lane": lane, "latency_ms": lat_b, "input_tokens": req.token_estimate, "output_tokens": expected_output, "modality": req.modality, "image_count": req.image_count, "page_count": req.page_count})

    dur_a = sum(r["latency_ms"] for r in run_a_results)
    dur_b = sum(r["latency_ms"] for r in run_b_results)

    metrics_a = collect_metrics(run_a_results, total_duration_ms=dur_a)
    metrics_b = collect_metrics(run_b_results, total_duration_ms=dur_b)

    speedup = round(metrics_a["p95_latency_ms"] / max(metrics_b["p95_latency_ms"], 1), 1)
    cost_savings = round((1 - metrics_b.get("gaudi_overdrive_utilization_pct", 0) / 100 * 2.5) * 100, 1)

    return {
        "profile": profile,
        "request_count": len(requests),
        "run_a": {
            "label": "Xeon 6 Only",
            "description": "All requests forced to Intel Xeon 6 — no GPU acceleration",
            "p95_latency_ms": metrics_a["p95_latency_ms"],
            "requests_per_second": metrics_a["requests_per_second"],
            "route_counts": metrics_a["route_counts"],
            "total_duration_ms": dur_a,
        },
        "run_b": {
            "label": "Xeon 6 + Gaudi",
            "description": "Intelligent routing — small tasks on Xeon 6, heavy tasks on Gaudi",
            "p95_latency_ms": metrics_b["p95_latency_ms"],
            "requests_per_second": metrics_b["requests_per_second"],
            "route_counts": metrics_b["route_counts"],
            "total_duration_ms": dur_b,
        },
        "speedup": speedup,
        "insight": f"Adding Intel Gaudi delivers {speedup}x faster p95 latency. Heavy generation tasks that take {int(metrics_a['p95_latency_ms'])}ms on CPU-only complete in {int(metrics_b['p95_latency_ms'])}ms with Gaudi acceleration.",
    }
