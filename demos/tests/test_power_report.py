#!/usr/bin/env python3
"""Stage 7: Power Report Writer — TDD Red Phase"""

import sys
import json
import pytest


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


def _sample_metrics():
    return {
        "run_id": "run-test-001",
        "workload_profile": "incident_storm",
        "power_mode": "drive",
        "total_requests": 25,
        "completed_requests": 25,
        "failed_requests": 0,
        "route_counts": {"eco": 8, "performance": 10, "overdrive": 7},
        "total_input_tokens_estimate": 125000,
        "total_output_tokens_estimate": 25000,
        "requests_per_second": 5.0,
        "estimated_tokens_per_second": 5000.0,
        "p50_latency_ms": 150.0,
        "p95_latency_ms": 800.0,
        "p99_latency_ms": 1200.0,
        "min_latency_ms": 50.0,
        "max_latency_ms": 1500.0,
        "total_duration_ms": 5000.0,
        "xeon_eco_utilization_pct": 32.0,
        "xeon_performance_utilization_pct": 40.0,
        "gaudi_overdrive_utilization_pct": 28.0,
    }


class TestPowerReportJSON:

    def test_generate_json(self):
        from overdrive.power_report import generate_json_report
        report = generate_json_report(_sample_metrics())
        assert isinstance(report, str)
        parsed = json.loads(report)
        assert parsed["run_id"] == "run-test-001"

    def test_json_has_all_sections(self):
        from overdrive.power_report import generate_json_report
        parsed = json.loads(generate_json_report(_sample_metrics()))
        assert "run_id" in parsed
        assert "route_counts" in parsed
        assert "p50_latency_ms" in parsed
        assert "requests_per_second" in parsed


class TestPowerReportMarkdown:

    def test_generate_markdown(self):
        from overdrive.power_report import generate_markdown_report
        md = generate_markdown_report(_sample_metrics())
        assert isinstance(md, str)
        assert "# Inference" in md

    def test_markdown_has_run_summary(self):
        from overdrive.power_report import generate_markdown_report
        md = generate_markdown_report(_sample_metrics())
        assert "Run Summary" in md
        assert "incident_storm" in md

    def test_markdown_has_route_distribution(self):
        from overdrive.power_report import generate_markdown_report
        md = generate_markdown_report(_sample_metrics())
        assert "Route Distribution" in md
        assert "Xeon" in md
        assert "Gaudi" in md

    def test_markdown_has_throughput(self):
        from overdrive.power_report import generate_markdown_report
        md = generate_markdown_report(_sample_metrics())
        assert "Throughput" in md
        assert "requests" in md.lower() or "Requests" in md

    def test_markdown_has_latency(self):
        from overdrive.power_report import generate_markdown_report
        md = generate_markdown_report(_sample_metrics())
        assert "Latency" in md
        assert "p50" in md or "p95" in md

    def test_markdown_labels_simulated(self):
        from overdrive.power_report import generate_markdown_report
        md = generate_markdown_report(_sample_metrics())
        assert "simulated" in md.lower()

    def test_no_governance_language(self):
        from overdrive.power_report import generate_markdown_report
        md = generate_markdown_report(_sample_metrics())
        banned = ["governance", "compliance", "policy enforcement", "remediation", "admissibility"]
        for word in banned:
            assert word not in md.lower(), f"Report must not contain '{word}'"
