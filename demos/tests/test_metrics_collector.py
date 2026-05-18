#!/usr/bin/env python3
"""Stage 6: Metrics Collector — TDD Red Phase"""

import sys
import pytest


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


def _make_result(lane, latency_ms, input_tokens, output_tokens):
    return {
        "lane": lane,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


class TestMetricsCollector:

    def test_importable(self):
        from overdrive.metrics_collector import collect_metrics
        assert collect_metrics is not None

    def test_returns_dict(self):
        from overdrive.metrics_collector import collect_metrics
        results = [_make_result("eco", 100, 500, 50) for _ in range(10)]
        m = collect_metrics(results, total_duration_ms=1000)
        assert isinstance(m, dict)

    def test_has_route_counts(self):
        from overdrive.metrics_collector import collect_metrics
        results = [
            _make_result("eco", 100, 500, 50),
            _make_result("eco", 120, 600, 60),
            _make_result("performance", 200, 1000, 100),
        ]
        m = collect_metrics(results, total_duration_ms=500)
        assert m["route_counts"]["eco"] == 2
        assert m["route_counts"]["performance"] == 1

    def test_has_latency_percentiles(self):
        from overdrive.metrics_collector import collect_metrics
        results = [_make_result("eco", i * 10, 500, 50) for i in range(1, 101)]
        m = collect_metrics(results, total_duration_ms=5000)
        assert "p50_latency_ms" in m
        assert "p95_latency_ms" in m
        assert "p99_latency_ms" in m
        assert m["p50_latency_ms"] > 0
        assert m["p95_latency_ms"] >= m["p50_latency_ms"]
        assert m["p99_latency_ms"] >= m["p95_latency_ms"]

    def test_has_rps(self):
        from overdrive.metrics_collector import collect_metrics
        results = [_make_result("eco", 100, 500, 50) for _ in range(100)]
        m = collect_metrics(results, total_duration_ms=10000)
        assert "requests_per_second" in m
        assert m["requests_per_second"] == pytest.approx(10.0, rel=0.01)

    def test_has_tokens_per_second(self):
        from overdrive.metrics_collector import collect_metrics
        results = [_make_result("eco", 100, 500, 50) for _ in range(10)]
        m = collect_metrics(results, total_duration_ms=1000)
        assert "estimated_tokens_per_second" in m
        assert m["estimated_tokens_per_second"] > 0

    def test_has_total_tokens(self):
        from overdrive.metrics_collector import collect_metrics
        results = [_make_result("eco", 100, 500, 50) for _ in range(10)]
        m = collect_metrics(results, total_duration_ms=1000)
        assert m["total_input_tokens_estimate"] == 5000
        assert m["total_output_tokens_estimate"] == 500

    def test_has_utilization(self):
        from overdrive.metrics_collector import collect_metrics
        results = [
            _make_result("eco", 100, 500, 50),
            _make_result("performance", 200, 1000, 100),
            _make_result("overdrive", 300, 2000, 200),
        ]
        m = collect_metrics(results, total_duration_ms=1000)
        assert "xeon_eco_utilization_pct" in m
        assert "xeon_performance_utilization_pct" in m
        assert "gaudi_overdrive_utilization_pct" in m

    def test_has_min_max_latency(self):
        from overdrive.metrics_collector import collect_metrics
        results = [_make_result("eco", lat, 500, 50) for lat in [50, 100, 200, 500]]
        m = collect_metrics(results, total_duration_ms=1000)
        assert m["min_latency_ms"] == 50
        assert m["max_latency_ms"] == 500

    def test_has_request_counts(self):
        from overdrive.metrics_collector import collect_metrics
        results = [_make_result("eco", 100, 500, 50) for _ in range(10)]
        m = collect_metrics(results, total_duration_ms=1000)
        assert m["total_requests"] == 10
        assert m["completed_requests"] == 10
