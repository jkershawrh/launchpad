#!/usr/bin/env python3
"""Stage 10: Multimodal E2E + Regression — TDD"""

import sys
import json
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")


class TestMultimodalE2EDashboardStorm:

    def test_overdrive_dashboard_storm_completes(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="dashboard_storm", mode="overdrive", seed=42)
        assert result["total_requests"] == 1000
        assert result["completed_requests"] == 1000

    def test_dashboard_storm_has_multimodal_metrics(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="dashboard_storm", mode="drive", seed=42)
        assert result["total_images"] > 0
        assert "modality_counts" in result
        assert "screenshot" in result["modality_counts"]

    def test_dashboard_storm_routes_to_both_lanes(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="dashboard_storm", mode="drive", seed=42)
        rc = result["route_counts"]
        assert rc.get("eco", 0) > 0 or rc.get("performance", 0) > 0
        assert rc.get("overdrive", 0) > 0

    def test_dashboard_storm_report_has_multimodal_section(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="dashboard_storm", mode="drive", seed=42)
        assert "Multimodal Summary" in result["report_md"]
        assert "Modality Distribution" in result["report_md"]

    def test_dashboard_storm_report_json_valid(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="dashboard_storm", mode="drive", seed=42)
        parsed = json.loads(result["report_json"])
        assert parsed["total_requests"] == 25


class TestMultimodalE2ETokenCannon:

    def test_token_cannon_multimodal_biases_overdrive(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="token_cannon_multimodal", mode="boost", seed=42)
        rc = result["route_counts"]
        total = result["total_requests"]
        overdrive_pct = rc.get("overdrive", 0) / total
        assert overdrive_pct > 0.5


class TestMultimodalE2EVisualRag:

    def test_visual_rag_barrage_has_both_modalities(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="visual_rag_barrage", mode="drive", seed=42)
        mc = result["modality_counts"]
        assert len(mc) >= 2


class TestExistingDemoRegression:

    def test_text_incident_storm_still_works(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert result["completed_requests"] == 5
        assert result["route_counts"]

    def test_text_rag_barrage_still_works(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="rag_barrage", mode="standby", seed=42)
        assert result["completed_requests"] == 5

    def test_existing_routing_engine_still_works(self):
        from pathlib import Path
        from overdrive.engine import OverdriveEngine
        from overdrive.models import InferenceRequest
        project_root = Path(__file__).parent.parent
        engine = OverdriveEngine(
            config_path=project_root / "gateway" / "overdrive" / "config.yaml",
            rubric_dir=project_root / "tests" / "rubrics" / "routes",
        )
        req = InferenceRequest(request_id="regression-mm-001", task_type="classification", priority="normal", token_estimate=1000, latency_target_ms=8000)
        decision = engine.evaluate(req)
        assert decision.selected_route == "eco"

    def test_no_governance_language_in_report(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="dashboard_storm", mode="standby", seed=42)
        md = result["report_md"].lower()
        banned = ["governance", "compliance", "remediation", "admissibility", "authority"]
        for word in banned:
            assert word not in md, f"Report must not contain '{word}'"


class TestMockMultimodalEndpoint:

    def test_endpoint_importable(self):
        from overdrive.multimodal_endpoint import MockMultimodalEndpoint
        assert MockMultimodalEndpoint is not None

    def test_deterministic_response(self):
        from overdrive.multimodal_endpoint import MockMultimodalEndpoint
        ep = MockMultimodalEndpoint(seed=42)
        a = ep.respond("screenshot_summary", "req-001")
        b = ep.respond("screenshot_summary", "req-001")
        assert a["response_text"] == b["response_text"]

    def test_different_tasks_different_responses(self):
        from overdrive.multimodal_endpoint import MockMultimodalEndpoint
        ep = MockMultimodalEndpoint(seed=42)
        a = ep.respond("screenshot_summary", "req-001")
        b = ep.respond("image_classification", "req-001")
        assert a["response_text"] != b["response_text"]

    def test_response_has_required_fields(self):
        from overdrive.multimodal_endpoint import MockMultimodalEndpoint
        ep = MockMultimodalEndpoint(seed=42)
        r = ep.respond("chart_interpretation", "req-001")
        assert "response_text" in r
        assert "task_type" in r
        assert r["source"] == "synthetic"
