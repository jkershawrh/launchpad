#!/usr/bin/env python3
"""Tests for gateway postprocessor functions."""
import pytest
import sys
from pathlib import Path


@pytest.fixture
def postprocess(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        if "router" in sys.modules:
            yield sys.modules["router"]._postprocess_result
        else:
            import router
            yield router._postprocess_result
    finally:
        sys.path.remove(gw)


class TestSearchPostprocessor:
    def test_search_converts_chat_to_results(self, postprocess):
        result = {"choices": [{"message": {"content": "1. Intel AMX accelerates AI workloads with hardware matrix ops.\n\n2. Gaudi provides GPU acceleration for large models."}}]}
        processed = postprocess("search", result, "What is AMX?")
        assert processed["object"] == "search_results"
        assert len(processed["results"]) > 0

    def test_search_results_have_rank_and_score(self, postprocess):
        result = {"choices": [{"message": {"content": "1. First relevant fact about the topic.\n\n2. Second relevant fact about the topic."}}]}
        processed = postprocess("search", result, "test")
        for r in processed["results"]:
            assert "rank" in r
            assert "score" in r
            assert "text" in r

    def test_search_passthrough_if_already_structured(self, postprocess):
        result = {"results": [{"rank": 1, "text": "already structured"}]}
        processed = postprocess("search", result, "test")
        assert processed["results"][0]["text"] == "already structured"


class TestClassificationPostprocessor:
    def test_classification_extracts_label_and_score(self, postprocess):
        result = {"choices": [{"message": {"content": "Technical, Confidence Score: 0.95"}}]}
        processed = postprocess("classification", result, "some alert")
        assert "predictions" in processed
        assert len(processed["predictions"]) > 0
        assert processed["predictions"][0]["label"] == "Technical"

    def test_classification_handles_percentage(self, postprocess):
        result = {"choices": [{"message": {"content": "Operational: 85%"}}]}
        processed = postprocess("classification", result, "test")
        preds = processed["predictions"]
        assert len(preds) > 0

    def test_classification_fallback_to_raw_text(self, postprocess):
        result = {"choices": [{"message": {"content": "This is a random response with no known labels"}}]}
        processed = postprocess("classification", result, "test")
        assert "predictions" in processed
        assert len(processed["predictions"]) > 0

    def test_classification_passthrough_if_has_predictions(self, postprocess):
        result = {"predictions": [{"label": "Technical", "score": 0.9}]}
        processed = postprocess("classification", result, "test")
        assert processed["predictions"][0]["label"] == "Technical"


class TestGovernancePostprocessor:
    def test_governance_deny_for_destructive(self, postprocess):
        result = {"choices": [{"message": {"content": "This action should be reviewed."}}]}
        processed = postprocess("governance", result, "Delete the production namespace")
        assert processed["decision"] == "deny"
        assert processed["risk_level"] == "critical"

    def test_governance_escalate_for_production(self, postprocess):
        result = {"choices": [{"message": {"content": "Needs review."}}]}
        processed = postprocess("governance", result, "Restart the pods in production")
        assert processed["decision"] == "escalate"
        assert processed["risk_level"] == "high"

    def test_governance_approve_for_readonly(self, postprocess):
        result = {"choices": [{"message": {"content": "Safe action."}}]}
        processed = postprocess("governance", result, "Read the logs from gateway pods")
        assert processed["decision"] == "approve"
        assert processed["risk_level"] == "low"


class TestPolicyPostprocessor:
    def test_policy_fail_for_destructive(self, postprocess):
        result = {"choices": [{"message": {"content": "Reviewed."}}]}
        processed = postprocess("policy", result, "Delete the production namespace")
        assert processed["verdict"] == "fail"
        assert len(processed["violations"]) > 0

    def test_policy_pass_for_safe(self, postprocess):
        result = {"choices": [{"message": {"content": "All good."}}]}
        processed = postprocess("policy", result, "Read the logs from gateway pods")
        assert processed["verdict"] == "pass"
        assert len(processed["violations"]) == 0

    def test_policy_analysis_matches_verdict(self, postprocess):
        result = {"choices": [{"message": {"content": "Reviewed."}}]}
        processed = postprocess("policy", result, "Delete everything")
        assert "FAIL" in processed["analysis"]
        assert processed["verdict"] == "fail"
