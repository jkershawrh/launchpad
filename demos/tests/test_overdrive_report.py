#!/usr/bin/env python3
"""Tests for Overdrive build and route reports."""

import pytest
import sys
from pathlib import Path


@pytest.fixture
def report_module(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.report as rpt
        importlib.reload(rpt)
        yield rpt
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


class TestBuildReport:
    def test_green_when_all_pass(self, report_module):
        results = {
            "request_model": {"tests": 8, "failures": 0},
            "rubric_evaluator": {"tests": 12, "failures": 0},
            "router": {"tests": 10, "failures": 0},
        }
        report = report_module.build_report(results)
        assert report["build_status"] == "green"
        assert len(report["blocking"]) == 0

    def test_red_when_failures(self, report_module):
        results = {
            "request_model": {"tests": 8, "failures": 0},
            "rubric_evaluator": {"tests": 12, "failures": 0},
            "router": {"tests": 10, "failures": 1},
        }
        report = report_module.build_report(results)
        assert report["build_status"] == "red"
        assert "router" in report["blocking"]

    def test_stages_present(self, report_module):
        results = {
            "request_model": {"tests": 8, "failures": 0},
            "router": {"tests": 10, "failures": 0},
        }
        report = report_module.build_report(results)
        assert len(report["stages"]) == 2
        assert report["stages"][0]["name"] == "request_model"
        assert report["stages"][0]["status"] == "green"


class TestRouteReport:
    def test_route_report_counts(self, report_module, models):
        decisions = [
            models.Decision("d1", "r1", "route", "eco", [], [], ["a"], "t"),
            models.Decision("d2", "r2", "route", "eco", [], [], ["a"], "t"),
            models.Decision("d3", "r3", "route", "performance", [], [], ["a"], "t"),
            models.Decision("d4", "r4", "route", "overdrive", [], [], ["a"], "t"),
            models.Decision("d5", "r5", "fallback", "performance", [], [], ["overdrive_failed"], "t"),
            models.Decision("d6", "r6", "indeterminate", None, [], [], ["unknown"], "t"),
        ]
        report = report_module.route_report("batch-001", decisions)
        assert report["batch_id"] == "batch-001"
        assert report["total_requests"] == 6
        assert report["routes"]["eco"] == 2
        assert report["routes"]["performance"] == 2
        assert report["routes"]["overdrive"] == 1
        assert report["fallbacks"] == 1
        assert report["indeterminate"] == 1

    def test_route_report_reason_codes(self, report_module, models):
        decisions = [
            models.Decision("d1", "r1", "route", "eco", [], [], ["task_type_classification", "eco_ready"], "t"),
            models.Decision("d2", "r2", "route", "eco", [], [], ["task_type_classification", "eco_ready"], "t"),
            models.Decision("d3", "r3", "route", "overdrive", [], [], ["task_type_long_summary", "overdrive_ready"], "t"),
        ]
        report = report_module.route_report("batch-002", decisions)
        assert "top_reason_codes" in report
        assert len(report["top_reason_codes"]) > 0

    def test_empty_batch(self, report_module):
        report = report_module.route_report("batch-empty", [])
        assert report["total_requests"] == 0
        assert report["routes"] == {}
