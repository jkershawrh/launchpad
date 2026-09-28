import copy
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/agentic_scale_score.py"
EVALUATION_PATH = ROOT / "evaluation/agentic-scale-v1.yaml"
EVALUATION = yaml.safe_load(EVALUATION_PATH.read_text())
EVALUATION_SHA256 = hashlib.sha256(EVALUATION_PATH.read_bytes()).hexdigest()
WORKLOAD = yaml.safe_load((ROOT / "contracts/agentic-workload-scale-v1.yaml").read_text())

spec = spec_from_file_location("agentic_scale_score", SCRIPT)
assert spec and spec.loader
scorer = module_from_spec(spec)
spec.loader.exec_module(scorer)


def _payload(source_state: str = "live") -> dict:
    results = []
    for index, case in enumerate(EVALUATION["cases"], start=1):
        results.append(
            {
                "case_id": case["id"],
                "journey_id": f"journey-{index:03d}",
                "status": "completed",
                "selected_workflow": case["expected_workflow"],
                "agents_involved": case["required_agents"],
                "evidence_types": case["required_evidence"],
                "policy_result": case["expected_policy_result"],
                "disposition": case["expected_disposition"],
                "review_required": case["human_review_required"],
                "automatic_action_executed": False,
                "journey_latency_ms": 1000 + index,
                "inference_latency_ms": 500 + index,
                "queue_ms": 50 + index,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
    return {
        "schema": "launchpad.agentic-workload-result/v1",
        "run_id": "test-run",
        "profile_id": "baseline",
        "source_state": source_state,
        "evaluation_set_id": EVALUATION["evaluation_set_id"],
        "evaluation_set_sha256": EVALUATION_SHA256,
        "results": results,
    }


def test_perfect_live_result_passes_every_gate():
    score = scorer.score_payload(_payload(), EVALUATION, WORKLOAD, EVALUATION_SHA256)

    assert score["certification_eligible"] is True
    assert score["passed"] is True
    assert all(score["gates"].values())
    assert score["metrics"]["unsupported_claims"] == 0
    assert score["metrics"]["automatic_actions"] == 0


def test_rehearsal_result_is_scored_but_cannot_pass_certification():
    score = scorer.score_payload(
        _payload("rehearsal"), EVALUATION, WORKLOAD, EVALUATION_SHA256
    )

    assert all(score["gates"].values())
    assert score["certification_eligible"] is False
    assert score["passed"] is False


def test_supported_claim_for_expected_denial_fails_quality_and_policy():
    payload = _payload()
    denied = next(result for result in payload["results"] if result["case_id"] == "C04")
    denied["disposition"] = "supported"
    denied["policy_result"] = "allow_recommendation"
    denied["automatic_action_executed"] = True

    score = scorer.score_payload(payload, EVALUATION, WORKLOAD, EVALUATION_SHA256)

    assert score["metrics"]["unsupported_claims"] == 1
    assert score["gates"]["unsupported_claims"] is False
    assert score["gates"]["policy"] is False
    assert score["gates"]["automatic_actions"] is False
    assert score["passed"] is False


def test_missing_required_evidence_fails_evidence_gate():
    payload = _payload()
    payload["results"][0]["evidence_types"] = []

    score = scorer.score_payload(payload, EVALUATION, WORKLOAD, EVALUATION_SHA256)

    assert score["gates"]["evidence"] is False
    assert score["passed"] is False


def test_duplicate_journey_or_negative_metric_is_rejected():
    duplicate = _payload()
    duplicate["results"][1]["journey_id"] = duplicate["results"][0]["journey_id"]
    with pytest.raises(scorer.ScoreError, match="duplicate journey_id"):
        scorer.score_payload(duplicate, EVALUATION, WORKLOAD, EVALUATION_SHA256)

    negative = copy.deepcopy(_payload())
    negative["results"][0]["queue_ms"] = -1
    with pytest.raises(scorer.ScoreError, match="queue_ms must be nonnegative"):
        scorer.score_payload(negative, EVALUATION, WORKLOAD, EVALUATION_SHA256)


def test_wrong_evaluation_hash_or_missing_case_is_rejected():
    wrong_hash = _payload()
    wrong_hash["evaluation_set_sha256"] = "0" * 64
    with pytest.raises(scorer.ScoreError, match="evaluation_set_sha256"):
        scorer.score_payload(wrong_hash, EVALUATION, WORKLOAD, EVALUATION_SHA256)

    incomplete = _payload()
    incomplete["results"].pop()
    with pytest.raises(scorer.ScoreError, match="evaluation cases are missing"):
        scorer.score_payload(incomplete, EVALUATION, WORKLOAD, EVALUATION_SHA256)
