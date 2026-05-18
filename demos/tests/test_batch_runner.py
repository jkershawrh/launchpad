#!/usr/bin/env python3
"""Stage 8: Batch Runner — TDD Red Phase"""

import sys
import pytest


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")


class TestBatchRunner:

    def test_importable(self):
        from overdrive.batch_runner import run_workload
        assert run_workload is not None

    def test_returns_result_dict(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert isinstance(result, dict)

    def test_result_has_run_id(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert "run_id" in result

    def test_result_has_metrics(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert "total_requests" in result
        assert "route_counts" in result
        assert "p50_latency_ms" in result
        assert "requests_per_second" in result

    def test_all_requests_processed(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert result["total_requests"] == 5
        assert result["completed_requests"] == 5

    def test_drive_mode_25_requests(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="drive", seed=42)
        assert result["total_requests"] == 25

    def test_result_has_profile_and_mode(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="rag_barrage", mode="standby", seed=42)
        assert result["workload_profile"] == "rag_barrage"
        assert result["power_mode"] == "standby"

    def test_result_has_reports(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert "report_json" in result
        assert "report_md" in result

    def test_deterministic(self):
        from overdrive.batch_runner import run_workload
        a = run_workload(profile="incident_storm", mode="standby", seed=42)
        b = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert a["route_counts"] == b["route_counts"]
        assert a["p50_latency_ms"] == b["p50_latency_ms"]
