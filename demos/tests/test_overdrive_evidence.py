#!/usr/bin/env python3
"""Tests for Overdrive evidence recorder."""

import pytest
import sys
import json
from pathlib import Path
from dataclasses import asdict


@pytest.fixture
def evidence_module(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.evidence as ev
        importlib.reload(ev)
        yield ev
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


class TestEvidenceRecorder:
    def test_record_decision(self, evidence_module, models):
        req = models.InferenceRequest("req-001", "classification", "normal", 1000, 8000)
        decision = models.Decision(
            "dec-001", "req-001", "route", "eco",
            ["eco"], [], ["task_type_classification"], "2026-05-08T00:00:00Z",
        )
        route_states = {"eco": {"healthy": True, "load": 0.0}}
        evidence = evidence_module.record_decision(decision, req, route_states)
        assert evidence.decision.decision_id == "dec-001"
        assert evidence.request.request_id == "req-001"
        assert evidence.route_states["eco"]["healthy"] is True

    def test_evidence_to_dict(self, evidence_module, models):
        req = models.InferenceRequest("req-001", "classification", "normal", 1000, 8000)
        check = models.Check("endpoint_health_pass", "eco", "pass", True)
        decision = models.Decision(
            "dec-001", "req-001", "route", "eco",
            ["eco", "performance", "overdrive"],
            [check],
            ["task_type_classification", "eco_ready"],
            "2026-05-08T00:00:00Z",
        )
        route_states = {"eco": {"healthy": True}}
        evidence = evidence_module.record_decision(decision, req, route_states)
        d = evidence_module.evidence_to_dict(evidence)
        assert isinstance(d, dict)
        assert d["decision_id"] == "dec-001"
        assert d["request_id"] == "req-001"
        assert d["outcome"] == "route"
        assert d["selected_route"] == "eco"
        assert len(d["evaluated_routes"]) == 3
        assert len(d["checks"]) == 1
        assert d["checks"][0]["name"] == "endpoint_health_pass"
        assert d["checks"][0]["result"] == "pass"
        assert "reason_codes" in d
        assert "timestamp" in d

    def test_evidence_json_serializable(self, evidence_module, models):
        req = models.InferenceRequest("req-002", "embedding", "normal", 6000, 5000)
        decision = models.Decision(
            "dec-002", "req-002", "route", "performance",
            ["performance"], [], ["task_type_embedding"], "2026-05-08T00:00:00Z",
        )
        evidence = evidence_module.record_decision(decision, req, {"performance": {"healthy": True}})
        d = evidence_module.evidence_to_dict(evidence)
        json_str = json.dumps(d)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["decision_id"] == "dec-002"
