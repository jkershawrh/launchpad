#!/usr/bin/env python3
"""Stage 5: Mock Timing Provider — TDD Red Phase"""

import sys
import pytest


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


class TestMockTimingProvider:

    def test_importable(self):
        from overdrive.timing_provider import MockTimingProvider
        assert MockTimingProvider is not None

    def test_returns_timing_dict(self):
        from overdrive.timing_provider import MockTimingProvider
        tp = MockTimingProvider(seed=42)
        t = tp.simulate(lane="eco", task_type="classification", token_estimate=1000, expected_output_tokens=100)
        assert isinstance(t, dict)

    def test_has_required_fields(self):
        from overdrive.timing_provider import MockTimingProvider
        tp = MockTimingProvider(seed=42)
        t = tp.simulate(lane="eco", task_type="classification", token_estimate=1000, expected_output_tokens=100)
        for key in ["latency_ms", "ttft_ms", "output_tokens_per_sec", "total_duration_ms"]:
            assert key in t, f"Missing key: {key}"

    def test_deterministic_with_same_seed(self):
        from overdrive.timing_provider import MockTimingProvider
        a = MockTimingProvider(seed=42).simulate("eco", "classification", 1000, 100)
        b = MockTimingProvider(seed=42).simulate("eco", "classification", 1000, 100)
        assert a == b

    def test_different_seeds_differ(self):
        from overdrive.timing_provider import MockTimingProvider
        a = MockTimingProvider(seed=42).simulate("eco", "classification", 1000, 100)
        b = MockTimingProvider(seed=99).simulate("eco", "classification", 1000, 100)
        assert a["latency_ms"] != b["latency_ms"]

    def test_gaudi_faster_than_xeon_for_large_tokens(self):
        from overdrive.timing_provider import MockTimingProvider
        tp = MockTimingProvider(seed=42)
        xeon = tp.simulate("performance", "long_summary", 30000, 2000)
        gaudi = tp.simulate("overdrive", "long_summary", 30000, 2000)
        assert gaudi["output_tokens_per_sec"] > xeon["output_tokens_per_sec"]

    def test_latency_scales_with_tokens(self):
        from overdrive.timing_provider import MockTimingProvider
        tp = MockTimingProvider(seed=42)
        small = tp.simulate("eco", "classification", 100, 10)
        large = tp.simulate("eco", "classification", 50000, 5000)
        assert large["latency_ms"] > small["latency_ms"]

    def test_all_values_positive(self):
        from overdrive.timing_provider import MockTimingProvider
        tp = MockTimingProvider(seed=42)
        t = tp.simulate("overdrive", "incident_rca", 30000, 2000)
        for key in ["latency_ms", "ttft_ms", "output_tokens_per_sec", "total_duration_ms"]:
            assert t[key] > 0, f"{key} must be positive"
