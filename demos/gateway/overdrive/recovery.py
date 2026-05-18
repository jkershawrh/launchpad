"""Recovery Demo — simulate Gaudi failure, fallback, and recovery."""

import random

from .workload_generator import generate_workload
from .engine import OverdriveEngine
from .timing_provider import MockTimingProvider
from pathlib import Path

_CONFIG = Path(__file__).parent / "config.yaml"
_RUBRICS = Path(__file__).parents[2] / "tests" / "rubrics" / "routes"

PHASE_SIZE = 8


def run_recovery_demo(seed: int = 42) -> dict:
    requests = generate_workload(profile="incident_storm", mode="drive", seed=seed)
    engine = OverdriveEngine(config_path=_CONFIG, rubric_dir=_RUBRICS)
    timing = MockTimingProvider(seed=seed)
    rng = random.Random(seed)

    phases = []
    all_results = []
    total_fallbacks = 0

    # Phase 1: Normal operation (Gaudi healthy)
    phase1_results = []
    for req in requests[:PHASE_SIZE]:
        decision = engine.evaluate(req)
        lane = decision.selected_route or "performance"
        t = timing.simulate(lane, req.task_type, req.token_estimate, max(50, req.token_estimate // 10))
        phase1_results.append({"lane": lane, "latency_ms": t["latency_ms"], "task_type": req.task_type, "fallback": False})
    all_results.extend(phase1_results)

    phases.append({
        "name": "normal",
        "label": "Normal Operation",
        "description": "All three Intel hardware lanes active. Requests route optimally — classification on Xeon 6 Eco, embeddings on Xeon 6 Performance, heavy generation on Gaudi Overdrive.",
        "gaudi_healthy": True,
        "requests": len(phase1_results),
        "route_counts": _count_lanes(phase1_results),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in phase1_results) / len(phase1_results), 1),
        "fallback_count": 0,
    })

    # Phase 2: Gaudi failure (force fallback to Xeon 6)
    engine.set_route_health("overdrive", False)
    phase2_results = []
    for req in requests[PHASE_SIZE:PHASE_SIZE * 2]:
        decision = engine.evaluate(req)
        lane = decision.selected_route or "performance"
        is_fallback = decision.outcome == "fallback"
        lat_multiplier = rng.uniform(2.5, 4.0) if is_fallback else 1.0
        t = timing.simulate(lane, req.task_type, req.token_estimate, max(50, req.token_estimate // 10))
        actual_latency = round(t["latency_ms"] * lat_multiplier, 1)
        phase2_results.append({"lane": lane, "latency_ms": actual_latency, "task_type": req.task_type, "fallback": is_fallback})
        if is_fallback:
            total_fallbacks += 1
    all_results.extend(phase2_results)

    phases.append({
        "name": "failure",
        "label": "Gaudi Offline — Fallback Active",
        "description": "Intel Gaudi accelerator goes offline. The routing engine automatically reroutes heavy tasks to Xeon 6 Performance lane. Latency increases but zero requests are dropped.",
        "gaudi_healthy": False,
        "requests": len(phase2_results),
        "route_counts": _count_lanes(phase2_results),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in phase2_results) / len(phase2_results), 1),
        "fallback_count": sum(1 for r in phase2_results if r["fallback"]),
    })

    # Phase 3: Recovery (Gaudi restored)
    engine.set_route_health("overdrive", True)
    phase3_results = []
    for req in requests[PHASE_SIZE * 2:PHASE_SIZE * 3]:
        decision = engine.evaluate(req)
        lane = decision.selected_route or "performance"
        t = timing.simulate(lane, req.task_type, req.token_estimate, max(50, req.token_estimate // 10))
        phase3_results.append({"lane": lane, "latency_ms": t["latency_ms"], "task_type": req.task_type, "fallback": False})
    all_results.extend(phase3_results)

    phases.append({
        "name": "recovery",
        "label": "Gaudi Restored — Normal Routing Resumed",
        "description": "Intel Gaudi comes back online. The routing engine detects recovery and resumes optimal routing. Heavy generation tasks return to Gaudi with full throughput.",
        "gaudi_healthy": True,
        "requests": len(phase3_results),
        "route_counts": _count_lanes(phase3_results),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in phase3_results) / len(phase3_results), 1),
        "fallback_count": 0,
    })

    return {
        "status": "completed",
        "phases": phases,
        "total_requests": len(all_results),
        "requests_dropped": 0,
        "total_fallbacks": total_fallbacks,
        "insight": f"During Gaudi failure, {total_fallbacks} requests were rerouted to Xeon 6. Zero requests dropped. Latency increased {round(phases[1]['avg_latency_ms'] / max(phases[0]['avg_latency_ms'], 1), 1)}x during fallback, then returned to normal after recovery.",
    }


def _count_lanes(results):
    from collections import Counter
    return dict(Counter(r["lane"] for r in results))
