#!/usr/bin/env python3
"""Score 501 workload results against the immutable evaluation set."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALUATION = ROOT / "evaluation/agentic-scale-v1.yaml"
DEFAULT_WORKLOAD_CONTRACT = ROOT / "contracts/agentic-workload-scale-v1.yaml"
ALLOWED_SOURCE_STATES = {"live", "rehearsal", "offline", "unavailable"}
REQUIRED_RESULT_FIELDS = {
    "case_id",
    "journey_id",
    "status",
    "selected_workflow",
    "agents_involved",
    "evidence_types",
    "policy_result",
    "disposition",
    "review_required",
    "automatic_action_executed",
    "journey_latency_ms",
    "inference_latency_ms",
    "queue_ms",
    "input_tokens",
    "output_tokens",
}


class ScoreError(ValueError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScoreError(f"{path} must contain a YAML mapping")
    return value


def nearest_rank_p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def percentage(numerator: int, denominator: int) -> float:
    return round((100 * numerator / denominator), 2) if denominator else 0.0


def validate_payload(
    payload: dict[str, Any],
    expected_cases: set[str],
    expected_evaluation_id: str,
    expected_evaluation_sha256: str | None,
    allowed_profiles: set[str],
) -> None:
    if payload.get("evaluation_set_id") != expected_evaluation_id:
        raise ScoreError("evaluation_set_id does not match the selected evaluation set")
    if (
        expected_evaluation_sha256 is not None
        and payload.get("evaluation_set_sha256") != expected_evaluation_sha256
    ):
        raise ScoreError("evaluation_set_sha256 does not match the selected evaluation set")
    if payload.get("profile_id") not in allowed_profiles:
        raise ScoreError("profile_id is not defined by the workload contract")
    if payload.get("source_state") not in ALLOWED_SOURCE_STATES:
        raise ScoreError("source_state is not recognized")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise ScoreError("results must be a non-empty list")
    journey_ids: set[str] = set()
    observed_cases: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            raise ScoreError("each result must be an object")
        missing = REQUIRED_RESULT_FIELDS - set(result)
        if missing:
            raise ScoreError(f"result {result.get('case_id')} is missing {sorted(missing)}")
        if result["case_id"] not in expected_cases:
            raise ScoreError(f"unknown case_id: {result['case_id']}")
        observed_cases.add(result["case_id"])
        if result["journey_id"] in journey_ids:
            raise ScoreError(f"duplicate journey_id: {result['journey_id']}")
        journey_ids.add(result["journey_id"])
        for field in (
            "journey_latency_ms",
            "inference_latency_ms",
            "queue_ms",
            "input_tokens",
            "output_tokens",
        ):
            if not isinstance(result[field], (int, float)) or result[field] < 0:
                raise ScoreError(f"{field} must be nonnegative")
        if not isinstance(result["agents_involved"], list):
            raise ScoreError("agents_involved must be a list")
        if not isinstance(result["evidence_types"], list):
            raise ScoreError("evidence_types must be a list")
    missing_cases = expected_cases - observed_cases
    if missing_cases:
        raise ScoreError(f"evaluation cases are missing: {sorted(missing_cases)}")


def score_payload(
    payload: dict[str, Any],
    evaluation: dict[str, Any],
    workload_contract: dict[str, Any],
    evaluation_sha256: str | None = None,
) -> dict[str, Any]:
    expected = {case["id"]: case for case in evaluation["cases"]}
    allowed_profiles = {
        profile["id"] for profile in workload_contract["workload_profiles"]
    }
    validate_payload(
        payload,
        set(expected),
        evaluation["evaluation_set_id"],
        evaluation_sha256,
        allowed_profiles,
    )
    results = payload["results"]
    completed = [result for result in results if result["status"] == "completed"]
    exact_disposition = 0
    policy_agreement = 0
    workflow_agreement = 0
    review_state_agreement = 0
    evidence_complete = 0
    agents_complete = 0
    unsupported_claims = 0
    automatic_actions = 0
    for result in results:
        case = expected[result["case_id"]]
        exact_disposition += result["disposition"] == case["expected_disposition"]
        policy_agreement += result["policy_result"] == case["expected_policy_result"]
        workflow_agreement += result["selected_workflow"] == case["expected_workflow"]
        review_state_agreement += result["review_required"] == case["human_review_required"]
        evidence_complete += set(case["required_evidence"]) <= set(result["evidence_types"])
        agents_complete += set(case["required_agents"]) <= set(result["agents_involved"])
        unsupported_claims += (
            result["disposition"] == "supported"
            and case["expected_disposition"] in {"denied", "inconclusive"}
        )
        automatic_actions += bool(result["automatic_action_executed"])
    total = len(results)
    metrics = {
        "total_results": total,
        "completed_results": len(completed),
        "success_rate_percent": percentage(len(completed), total),
        "supported_decision_agreement_percent": percentage(exact_disposition, total),
        "policy_agreement_percent": percentage(policy_agreement, total),
        "workflow_agreement_percent": percentage(workflow_agreement, total),
        "review_state_agreement_percent": percentage(review_state_agreement, total),
        "evidence_completeness_percent": percentage(evidence_complete, total),
        "agent_completeness_percent": percentage(agents_complete, total),
        "unsupported_claims": unsupported_claims,
        "automatic_actions": automatic_actions,
        "journey_p95_ms": nearest_rank_p95(
            [float(result["journey_latency_ms"]) for result in completed]
        ),
        "inference_p95_ms": nearest_rank_p95(
            [float(result["inference_latency_ms"]) for result in completed]
        ),
        "queue_p95_ms": nearest_rank_p95([float(result["queue_ms"]) for result in completed]),
        "input_tokens": sum(result["input_tokens"] for result in completed),
        "output_tokens": sum(result["output_tokens"] for result in completed),
    }
    objectives = workload_contract["service_objectives"]
    quality = workload_contract["quality_gate"]
    gates = {
        "success_rate": metrics["success_rate_percent"]
        >= objectives["journey"]["minimum_success_rate_percent"],
        "journey_p95": metrics["journey_p95_ms"] is not None
        and metrics["journey_p95_ms"] <= objectives["journey"]["maximum_p95_latency_ms"],
        "inference_p95": metrics["inference_p95_ms"] is not None
        and metrics["inference_p95_ms"]
        <= objectives["inference"]["maximum_p95_latency_ms"],
        "queue_p95": metrics["queue_p95_ms"] is not None
        and metrics["queue_p95_ms"] <= objectives["inference"]["maximum_queue_p95_ms"],
        "quality": metrics["supported_decision_agreement_percent"]
        >= quality["minimum_supported_decision_rate_percent"],
        "policy": metrics["policy_agreement_percent"]
        >= quality["deterministic_policy_agreement_percent"],
        "evidence": metrics["evidence_completeness_percent"] == 100,
        "review_state": metrics["review_state_agreement_percent"]
        >= quality["review_required_state_rate_percent"],
        "unsupported_claims": metrics["unsupported_claims"] == 0,
        "automatic_actions": metrics["automatic_actions"]
        == quality["automatic_action_execution_count"],
    }
    certification_eligible = payload["source_state"] == "live"
    return {
        "schema": "launchpad.agentic-workload-score/v1",
        "run_id": payload["run_id"],
        "profile_id": payload["profile_id"],
        "source_state": payload["source_state"],
        "certification_eligible": certification_eligible,
        "metrics": metrics,
        "gates": gates,
        "passed": certification_eligible and all(gates.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    parser.add_argument("--contract", type=Path, default=DEFAULT_WORKLOAD_CONTRACT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.result.read_text(encoding="utf-8"))
    evaluation_bytes = args.evaluation.read_bytes()
    evaluation = yaml.safe_load(evaluation_bytes)
    if not isinstance(evaluation, dict):
        raise ScoreError(f"{args.evaluation} must contain a YAML mapping")
    scored = score_payload(
        payload,
        evaluation,
        load_yaml(args.contract),
        hashlib.sha256(evaluation_bytes).hexdigest(),
    )
    rendered = json.dumps(scored, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
