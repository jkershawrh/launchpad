#!/usr/bin/env python3
"""Tests for Overdrive lane evaluation engine — the 10 fixtures from spec."""

import os
import pytest
import sys
from pathlib import Path


@pytest.fixture(autouse=True)
def set_test_env():
    os.environ.setdefault("LITELLM_API_BASE", "https://test-litellm.example.com")
    os.environ.setdefault("LITELLM_API_KEY", "test-key")


@pytest.fixture
def engine_instance(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.engine as eng
        importlib.reload(eng)
        engine = eng.OverdriveEngine(
            config_path=project_root / "gateway" / "overdrive" / "config.yaml",
            rubric_dir=project_root / "tests" / "rubrics" / "routes",
        )
        yield engine
    finally:
        sys.path.remove(gw)


@pytest.fixture
def models(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.models as m
        importlib.reload(m)
        yield m
    finally:
        sys.path.remove(gw)


class TestFixture1_ClassificationToEco:
    def test_routes_to_eco(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="fix-001", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.selected_route == "eco"
        assert decision.outcome == "route"

    def test_has_reason_codes(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="fix-001", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        decision = engine_instance.evaluate(req)
        assert len(decision.reason_codes) > 0


class TestFixture2_EmbeddingToPerformance:
    def test_routes_to_performance(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="fix-002", task_type="embedding",
            priority="normal", token_estimate=6000, latency_target_ms=5000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.selected_route == "performance"
        assert decision.outcome == "route"


class TestFixture3_LongSummaryToOverdrive:
    def test_routes_to_overdrive(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="fix-003", task_type="long_summary",
            priority="high", token_estimate=24000, latency_target_ms=5000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.selected_route == "overdrive"
        assert decision.outcome == "route"


class TestFixture4_IncidentRCAToOverdrive:
    def test_routes_to_overdrive(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="fix-004", task_type="incident_rca",
            priority="critical", token_estimate=32000, latency_target_ms=5000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.selected_route == "overdrive"
        assert decision.outcome == "route"


class TestFixture5_OverdriveUnhealthyFallback:
    def test_falls_back_to_performance(self, engine_instance, models):
        engine_instance.set_route_health("overdrive", False)
        req = models.InferenceRequest(
            request_id="fix-005", task_type="long_summary",
            priority="high", token_estimate=24000, latency_target_ms=5000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.selected_route == "performance"
        assert decision.outcome == "fallback"
        assert any("overdrive" in rc.lower() for rc in decision.reason_codes)
        engine_instance.set_route_health("overdrive", True)


class TestFixture6_PerformanceUnhealthyFallback:
    def test_falls_back_to_eco(self, engine_instance, models):
        engine_instance.set_route_health("performance", False)
        req = models.InferenceRequest(
            request_id="fix-006", task_type="short_summary",
            priority="normal", token_estimate=3000, latency_target_ms=8000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.selected_route == "eco"
        assert decision.outcome == "fallback"
        engine_instance.set_route_health("performance", True)


class TestFixture7_UnknownTaskIndeterminate:
    def test_returns_indeterminate(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="fix-007", task_type="unknown",
            priority="normal", token_estimate=1000, latency_target_ms=5000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.outcome == "indeterminate"
        assert decision.selected_route is None


class TestFixture8_OverdriveTooSmall:
    def test_routes_to_eco_not_overdrive(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="fix-008", task_type="classification",
            priority="critical", token_estimate=1000, latency_target_ms=8000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.selected_route == "eco"
        assert decision.outcome == "route"


class TestFixture9_AllRoutesUnhealthy:
    def test_returns_queue_or_indeterminate(self, engine_instance, models):
        engine_instance.set_route_health("eco", False)
        engine_instance.set_route_health("performance", False)
        engine_instance.set_route_health("overdrive", False)
        req = models.InferenceRequest(
            request_id="fix-009", task_type="long_summary",
            priority="high", token_estimate=24000, latency_target_ms=5000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.outcome in ("queue", "indeterminate")
        assert decision.selected_route is None
        engine_instance.set_route_health("eco", True)
        engine_instance.set_route_health("performance", True)
        engine_instance.set_route_health("overdrive", True)


class TestFixture10_BatchRouting:
    def test_batch_routes_correctly(self, engine_instance, models):
        requests = [
            models.InferenceRequest("b-001", "classification", "normal", 1000, 8000),
            models.InferenceRequest("b-002", "embedding", "normal", 6000, 5000),
            models.InferenceRequest("b-003", "long_summary", "high", 24000, 5000),
            models.InferenceRequest("b-004", "incident_rca", "critical", 32000, 5000),
            models.InferenceRequest("b-005", "unknown", "normal", 1000, 5000),
        ]
        decisions = [engine_instance.evaluate(r) for r in requests]
        routes = [d.selected_route for d in decisions]
        assert routes[0] == "eco"
        assert routes[1] == "performance"
        assert routes[2] == "overdrive"
        assert routes[3] == "overdrive"
        assert routes[4] is None
        outcomes = [d.outcome for d in decisions]
        assert outcomes.count("route") == 4
        assert outcomes.count("indeterminate") == 1


class TestEngineState:
    def test_get_route_state(self, engine_instance):
        state = engine_instance.get_route_state()
        assert "eco" in state
        assert "performance" in state
        assert "overdrive" in state
        assert state["eco"]["healthy"] is True

    def test_set_and_get_health(self, engine_instance):
        engine_instance.set_route_health("eco", False)
        state = engine_instance.get_route_state()
        assert state["eco"]["healthy"] is False
        engine_instance.set_route_health("eco", True)

    def test_decision_has_checks(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="chk-001", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        decision = engine_instance.evaluate(req)
        assert len(decision.checks) > 0
        assert all(hasattr(c, "result") for c in decision.checks)

    def test_decision_has_evaluated_routes(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="chk-002", task_type="long_summary",
            priority="high", token_estimate=24000, latency_target_ms=5000,
        )
        decision = engine_instance.evaluate(req)
        assert len(decision.evaluated_routes) > 0

    def test_decision_has_timestamp(self, engine_instance, models):
        req = models.InferenceRequest(
            request_id="chk-003", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        decision = engine_instance.evaluate(req)
        assert decision.timestamp is not None
        assert len(decision.timestamp) > 0
