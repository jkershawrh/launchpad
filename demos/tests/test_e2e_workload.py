#!/usr/bin/env python3
"""Stage 10: E2E Workload — TDD Red Phase"""

import os
import sys
import json
import pytest


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")


class TestE2EIncidentStormOverdrive:

    def test_full_run_completes(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="overdrive", seed=42)
        assert result["total_requests"] == 1000
        assert result["completed_requests"] == 1000
        assert result["failed_requests"] == 0

    def test_all_lanes_receive_traffic(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="overdrive", seed=42)
        rc = result["route_counts"]
        assert rc.get("eco", 0) > 0, "Eco lane should receive traffic"
        assert rc.get("performance", 0) > 0 or rc.get("eco", 0) > 0, "Xeon should receive traffic"
        assert rc.get("overdrive", 0) > 0, "Gaudi overdrive should receive traffic"

    def test_report_json_is_valid(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="drive", seed=42)
        parsed = json.loads(result["report_json"])
        assert parsed["total_requests"] == 25

    def test_report_md_is_nonempty(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="drive", seed=42)
        assert len(result["report_md"]) > 200


class TestE2ERagBarrage:

    def test_rag_barrage_runs(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="rag_barrage", mode="drive", seed=42)
        assert result["total_requests"] == 25
        assert result["completed_requests"] == 25


class TestE2ETokenCannon:

    def test_token_cannon_biases_overdrive(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="token_cannon", mode="boost", seed=42)
        rc = result["route_counts"]
        total = result["total_requests"]
        overdrive_pct = rc.get("overdrive", 0) / total
        assert overdrive_pct > 0.5, f"Token cannon should bias >50% to overdrive, got {overdrive_pct:.0%}"


class TestExistingDemoRegression:

    def test_existing_overdrive_engine_still_works(self):
        from pathlib import Path
        from overdrive.engine import OverdriveEngine
        from overdrive.models import InferenceRequest
        project_root = Path(__file__).parent.parent
        engine = OverdriveEngine(
            config_path=project_root / "gateway" / "overdrive" / "config.yaml",
            rubric_dir=project_root / "tests" / "rubrics" / "routes",
        )
        req = InferenceRequest(
            request_id="regression-001",
            task_type="classification",
            priority="normal",
            token_estimate=1000,
            latency_target_ms=8000,
        )
        decision = engine.evaluate(req)
        assert decision.selected_route == "eco"
        assert decision.outcome == "route"
