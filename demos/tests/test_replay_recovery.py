#!/usr/bin/env python3
"""Replay Comparison + Recovery Demo — TDD"""

import sys
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")


# ─── REPLAY COMPARISON ───

class TestReplayComparison:

    def test_replay_module_exists(self):
        from overdrive.replay import run_comparison
        assert run_comparison is not None

    def test_comparison_returns_two_runs(self):
        from overdrive.replay import run_comparison
        result = run_comparison(profile="incident_storm", seed=42)
        assert "run_a" in result
        assert "run_b" in result

    def test_run_a_is_xeon_only(self):
        from overdrive.replay import run_comparison
        result = run_comparison(profile="incident_storm", seed=42)
        assert result["run_a"]["label"] == "Xeon 6 Only"

    def test_run_b_is_xeon_plus_gaudi(self):
        from overdrive.replay import run_comparison
        result = run_comparison(profile="incident_storm", seed=42)
        assert result["run_b"]["label"] == "Xeon 6 + Gaudi"

    def test_gaudi_run_is_faster(self):
        from overdrive.replay import run_comparison
        result = run_comparison(profile="incident_storm", seed=42)
        assert result["run_b"]["p95_latency_ms"] < result["run_a"]["p95_latency_ms"]

    def test_comparison_has_summary(self):
        from overdrive.replay import run_comparison
        result = run_comparison(profile="incident_storm", seed=42)
        assert "speedup" in result
        assert result["speedup"] > 1


# ─── RECOVERY DEMO ───

class TestRecoveryDemo:

    def test_recovery_module_exists(self):
        from overdrive.recovery import run_recovery_demo
        assert run_recovery_demo is not None

    def test_recovery_has_three_phases(self):
        from overdrive.recovery import run_recovery_demo
        result = run_recovery_demo(seed=42)
        assert len(result["phases"]) == 3

    def test_phase_1_is_normal(self):
        from overdrive.recovery import run_recovery_demo
        result = run_recovery_demo(seed=42)
        assert result["phases"][0]["name"] == "normal"
        assert result["phases"][0]["gaudi_healthy"] is True

    def test_phase_2_is_failure(self):
        from overdrive.recovery import run_recovery_demo
        result = run_recovery_demo(seed=42)
        assert result["phases"][1]["name"] == "failure"
        assert result["phases"][1]["gaudi_healthy"] is False

    def test_phase_3_is_recovery(self):
        from overdrive.recovery import run_recovery_demo
        result = run_recovery_demo(seed=42)
        assert result["phases"][2]["name"] == "recovery"
        assert result["phases"][2]["gaudi_healthy"] is True

    def test_no_requests_dropped(self):
        from overdrive.recovery import run_recovery_demo
        result = run_recovery_demo(seed=42)
        assert result["requests_dropped"] == 0

    def test_fallback_count_during_failure(self):
        from overdrive.recovery import run_recovery_demo
        result = run_recovery_demo(seed=42)
        assert result["phases"][1]["fallback_count"] > 0


# ─── FRONTEND ───

class TestFrontendWiring:

    def test_replay_page_exists(self, project_root):
        assert (project_root / "frontend" / "src" / "pages" / "ReplayDemo.tsx").exists()

    def test_recovery_page_exists(self, project_root):
        assert (project_root / "frontend" / "src" / "pages" / "RecoveryDemo.tsx").exists()

    def test_routes_exist(self, project_root):
        app = (project_root / "frontend" / "src" / "App.tsx").read_text()
        assert "/replay" in app
        assert "/recovery" in app

    def test_nav_exists(self, project_root):
        layout = (project_root / "frontend" / "src" / "components" / "AppLayout.tsx").read_text()
        assert "/replay" in layout
        assert "/recovery" in layout
