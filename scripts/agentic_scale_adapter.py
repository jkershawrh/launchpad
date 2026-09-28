#!/usr/bin/env python3
"""Invoke the agentic workflow API and produce fail-closed 501 result records."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib import request


class AdapterError(ValueError):
    pass


def _required(mapping: dict[str, Any], field: str, context: str) -> Any:
    value = mapping.get(field)
    if value is None:
        raise AdapterError(f"{context}.{field} is unavailable")
    return value


def adapt_workflow_response(
    response: dict[str, Any], case_id: str, journey_id: str
) -> dict[str, Any]:
    """Translate one complete proof envelope without inventing missing values."""
    if response.get("case_id") != case_id or response.get("journey_id") != journey_id:
        raise AdapterError("workflow correlation does not match the requested journey")
    proof = _required(response, "proof", "response")
    evidence = _required(proof, "evidence", "proof")
    policy = _required(proof, "policy", "proof")
    inference = _required(proof, "inference", "proof")
    review = _required(proof, "human_review", "proof")
    if evidence.get("status") != "complete":
        raise AdapterError("proof.evidence is not complete")
    if policy.get("evaluation_status") != "evaluated":
        raise AdapterError("proof.policy is not evaluated")
    if inference.get("source_state") != "live":
        raise AdapterError("proof.inference is not live")
    if inference.get("telemetry_status") != "complete":
        raise AdapterError("proof.inference telemetry is not complete")
    evidence_types = []
    for item in evidence.get("items", []):
        evidence_type = item.get("evidence_type")
        if not evidence_type:
            raise AdapterError("proof.evidence item lacks evidence_type")
        evidence_types.append(evidence_type)
    steps = response.get("steps") or []
    status = "completed" if steps and all(s.get("status") == "completed" for s in steps) else "failed"
    return {
        "case_id": case_id,
        "journey_id": journey_id,
        "status": status,
        "selected_workflow": _required(response, "selected_workflow", "response"),
        "agents_involved": response.get("agents_involved") or [],
        "evidence_types": list(dict.fromkeys(evidence_types)),
        "policy_result": _required(policy, "result", "proof.policy"),
        "disposition": _required(policy, "disposition", "proof.policy"),
        "review_required": _required(review, "required", "proof.human_review"),
        "automatic_action_executed": _required(
            review, "automatic_action_executed", "proof.human_review"
        ),
        "journey_latency_ms": _required(response, "total_latency_ms", "response"),
        "inference_latency_ms": _required(
            inference, "latency_ms", "proof.inference"
        ),
        "queue_ms": _required(inference, "queue_ms", "proof.inference"),
        "input_tokens": _required(inference, "input_tokens", "proof.inference"),
        "output_tokens": _required(inference, "output_tokens", "proof.inference"),
    }


def invoke_workflow(
    base_url: str,
    case: dict[str, Any],
    journey_id: str,
    timeout_seconds: float,
    token: str | None = None,
) -> dict[str, Any]:
    """Call one workflow using only explicit correlation and bounded timeout."""
    body = json.dumps(
        {
            "query": case["prompt"],
            "workflow_type": case["expected_workflow"],
            "journey_id": journey_id,
            "case_id": case["id"],
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    http_request = request.Request(
        f"{base_url.rstrip('/')}/api/v1/workflow",
        data=body,
        headers=headers,
        method="POST",
    )
    started = time.monotonic()
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if time.monotonic() - started > timeout_seconds:
        raise AdapterError("workflow exceeded the bounded timeout")
    return adapt_workflow_response(payload, case["id"], journey_id)
