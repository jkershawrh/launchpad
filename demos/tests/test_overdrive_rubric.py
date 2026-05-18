#!/usr/bin/env python3
"""Tests for Overdrive rubric loader and evaluator — TDD RED phase."""

import pytest
import sys
from pathlib import Path


@pytest.fixture
def rubric_module(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.rubric as rubric
        importlib.reload(rubric)
        yield rubric
    finally:
        sys.path.remove(gw)


@pytest.fixture
def models_module(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.models as models
        importlib.reload(models)
        yield models
    finally:
        sys.path.remove(gw)


@pytest.fixture
def rubric_dir(project_root):
    return project_root / "tests" / "rubrics" / "routes"


class TestRubricLoader:
    def test_rubric_dir_exists(self, rubric_dir):
        assert rubric_dir.exists()

    def test_loads_three_rubrics(self, rubric_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        assert set(rubrics.keys()) == {"eco", "performance", "overdrive"}

    def test_rubric_has_required_checks(self, rubric_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        for name, rubric in rubrics.items():
            assert "required_checks" in rubric, f"{name} missing required_checks"
            assert len(rubric["required_checks"]) > 0, f"{name} has no checks"

    def test_eco_rubric_has_four_checks(self, rubric_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        assert len(rubrics["eco"]["required_checks"]) == 4

    def test_overdrive_rubric_has_six_checks(self, rubric_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        assert len(rubrics["overdrive"]["required_checks"]) == 6

    def test_overdrive_has_warn_conditions(self, rubric_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        assert "warn_conditions" in rubrics["overdrive"]


class TestRubricEvaluator:
    def test_eco_passes_for_classification(self, rubric_module, models_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        route = models_module.Route(
            route_id="eco", lane="eco", target_endpoint="mock://eco",
            capabilities=["classification", "short_summary"], max_token_estimate=4000, healthy=True,
        )
        req = models_module.InferenceRequest(
            request_id="t-001", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        checks = rubric_module.evaluate_route(req, route, rubrics["eco"])
        assert rubric_module.route_passes(checks)

    def test_eco_fails_for_large_task(self, rubric_module, models_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        route = models_module.Route(
            route_id="eco", lane="eco", target_endpoint="mock://eco",
            capabilities=["classification", "short_summary"], max_token_estimate=4000, healthy=True,
        )
        req = models_module.InferenceRequest(
            request_id="t-002", task_type="long_summary",
            priority="high", token_estimate=24000, latency_target_ms=5000,
        )
        checks = rubric_module.evaluate_route(req, route, rubrics["eco"])
        assert not rubric_module.route_passes(checks)

    def test_eco_fails_when_unhealthy(self, rubric_module, models_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        route = models_module.Route(
            route_id="eco", lane="eco", target_endpoint="mock://eco",
            capabilities=["classification"], max_token_estimate=4000, healthy=False,
        )
        req = models_module.InferenceRequest(
            request_id="t-003", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        checks = rubric_module.evaluate_route(req, route, rubrics["eco"])
        assert not rubric_module.route_passes(checks)

    def test_overdrive_passes_for_large_task(self, rubric_module, models_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        route = models_module.Route(
            route_id="overdrive", lane="overdrive", target_endpoint="mock://overdrive",
            capabilities=["long_summary", "incident_rca", "batch_summary"], max_token_estimate=64000, healthy=True,
        )
        req = models_module.InferenceRequest(
            request_id="t-004", task_type="long_summary",
            priority="high", token_estimate=24000, latency_target_ms=5000,
        )
        checks = rubric_module.evaluate_route(req, route, rubrics["overdrive"])
        assert rubric_module.route_passes(checks)

    def test_overdrive_fails_for_small_task(self, rubric_module, models_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        route = models_module.Route(
            route_id="overdrive", lane="overdrive", target_endpoint="mock://overdrive",
            capabilities=["long_summary", "incident_rca", "batch_summary"], max_token_estimate=64000, healthy=True,
        )
        req = models_module.InferenceRequest(
            request_id="t-005", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        checks = rubric_module.evaluate_route(req, route, rubrics["overdrive"])
        assert not rubric_module.route_passes(checks)

    def test_overdrive_fails_low_priority(self, rubric_module, models_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        route = models_module.Route(
            route_id="overdrive", lane="overdrive", target_endpoint="mock://overdrive",
            capabilities=["long_summary"], max_token_estimate=64000, healthy=True,
        )
        req = models_module.InferenceRequest(
            request_id="t-006", task_type="long_summary",
            priority="low", token_estimate=24000, latency_target_ms=5000,
        )
        checks = rubric_module.evaluate_route(req, route, rubrics["overdrive"])
        assert not rubric_module.route_passes(checks)

    def test_check_results_are_check_objects(self, rubric_module, models_module, rubric_dir):
        rubrics = rubric_module.load_rubrics(rubric_dir)
        route = models_module.Route(
            route_id="eco", lane="eco", target_endpoint="mock://eco",
            capabilities=["classification"], max_token_estimate=4000, healthy=True,
        )
        req = models_module.InferenceRequest(
            request_id="t-007", task_type="classification",
            priority="normal", token_estimate=1000, latency_target_ms=8000,
        )
        checks = rubric_module.evaluate_route(req, route, rubrics["eco"])
        assert all(hasattr(c, "name") and hasattr(c, "result") for c in checks)
