#!/usr/bin/env python3
"""Tests for StarGate Overdrive Lite data models — TDD RED phase."""

import pytest
import sys
from pathlib import Path
from dataclasses import asdict


@pytest.fixture
def overdrive_module(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.models as models
        importlib.reload(models)
        yield models
    finally:
        sys.path.remove(gw)


class TestInferenceRequest:
    def test_create_valid_request(self, overdrive_module):
        req = overdrive_module.InferenceRequest(
            request_id="req-001",
            task_type="classification",
            priority="normal",
            token_estimate=1000,
            latency_target_ms=8000,
        )
        assert req.request_id == "req-001"
        assert req.task_type == "classification"
        assert req.priority == "normal"
        assert req.token_estimate == 1000
        assert req.latency_target_ms == 8000
        assert req.prompt == ""
        assert req.metadata == {}

    def test_request_with_prompt(self, overdrive_module):
        req = overdrive_module.InferenceRequest(
            request_id="req-002",
            task_type="long_summary",
            priority="high",
            token_estimate=24000,
            latency_target_ms=5000,
            prompt="Summarize this document",
            metadata={"source": "test"},
        )
        assert req.prompt == "Summarize this document"
        assert req.metadata["source"] == "test"

    def test_request_serializable(self, overdrive_module):
        req = overdrive_module.InferenceRequest(
            request_id="req-003",
            task_type="embedding",
            priority="normal",
            token_estimate=6000,
            latency_target_ms=5000,
        )
        d = asdict(req)
        assert isinstance(d, dict)
        assert d["request_id"] == "req-003"
        assert d["task_type"] == "embedding"


class TestRoute:
    def test_create_route(self, overdrive_module):
        route = overdrive_module.Route(
            route_id="eco",
            lane="eco",
            target_endpoint="mock://eco",
            capabilities=["classification", "short_summary"],
            max_token_estimate=4000,
        )
        assert route.route_id == "eco"
        assert route.lane == "eco"
        assert route.healthy is True
        assert route.current_load == 0.0

    def test_route_unhealthy(self, overdrive_module):
        route = overdrive_module.Route(
            route_id="overdrive",
            lane="overdrive",
            target_endpoint="mock://overdrive",
            capabilities=["long_summary"],
            max_token_estimate=64000,
            healthy=False,
        )
        assert route.healthy is False

    def test_route_serializable(self, overdrive_module):
        route = overdrive_module.Route(
            route_id="performance",
            lane="performance",
            target_endpoint="mock://performance",
            capabilities=["embedding"],
            max_token_estimate=16000,
        )
        d = asdict(route)
        assert d["lane"] == "performance"


class TestCheck:
    def test_create_pass_check(self, overdrive_module):
        check = overdrive_module.Check(
            name="endpoint_health_pass",
            route="eco",
            result="pass",
            observed=True,
        )
        assert check.result == "pass"

    def test_create_fail_check(self, overdrive_module):
        check = overdrive_module.Check(
            name="token_estimate_within_limit",
            route="eco",
            result="fail",
            observed=24000,
            reason="token_estimate_exceeds_lane_max",
        )
        assert check.result == "fail"
        assert check.reason == "token_estimate_exceeds_lane_max"

    def test_create_warn_check(self, overdrive_module):
        check = overdrive_module.Check(
            name="fallback_unavailable",
            route="overdrive",
            result="warn",
        )
        assert check.result == "warn"


class TestDecision:
    def test_create_route_decision(self, overdrive_module):
        decision = overdrive_module.Decision(
            decision_id="dec-001",
            request_id="req-001",
            outcome="route",
            selected_route="eco",
            evaluated_routes=["eco", "performance", "overdrive"],
            checks=[],
            reason_codes=["task_type_classification"],
            timestamp="2026-05-08T00:00:00Z",
        )
        assert decision.outcome == "route"
        assert decision.selected_route == "eco"

    def test_indeterminate_decision(self, overdrive_module):
        decision = overdrive_module.Decision(
            decision_id="dec-002",
            request_id="req-002",
            outcome="indeterminate",
            selected_route=None,
            evaluated_routes=["eco", "performance", "overdrive"],
            checks=[],
            reason_codes=["unknown_task_type"],
            timestamp="2026-05-08T00:00:00Z",
        )
        assert decision.outcome == "indeterminate"
        assert decision.selected_route is None

    def test_decision_serializable(self, overdrive_module):
        decision = overdrive_module.Decision(
            decision_id="dec-003",
            request_id="req-003",
            outcome="fallback",
            selected_route="performance",
            evaluated_routes=["overdrive", "performance"],
            checks=[
                overdrive_module.Check(name="endpoint_health_pass", route="overdrive", result="fail", observed=False),
            ],
            reason_codes=["overdrive_unhealthy", "fallback_to_performance"],
            timestamp="2026-05-08T00:00:00Z",
        )
        d = asdict(decision)
        assert d["outcome"] == "fallback"
        assert len(d["checks"]) == 1
        assert d["checks"][0]["result"] == "fail"


class TestEvidence:
    def test_create_evidence(self, overdrive_module):
        req = overdrive_module.InferenceRequest(
            request_id="req-001", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        decision = overdrive_module.Decision(
            decision_id="dec-001", request_id="req-001",
            outcome="route", selected_route="eco",
            evaluated_routes=["eco"], checks=[], reason_codes=[],
            timestamp="2026-05-08T00:00:00Z",
        )
        evidence = overdrive_module.Evidence(
            decision=decision, request=req,
            route_states={"eco": {"healthy": True, "load": 0.0}},
        )
        assert evidence.decision.selected_route == "eco"
        assert evidence.route_states["eco"]["healthy"] is True
