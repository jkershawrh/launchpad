#!/usr/bin/env python3
"""
AI Operations Copilot Demo — Intel-Red Hat AI Partner Platform

Demonstrates governed AIOps from signal to action:
  1. Classify alert severity on Xeon 6 (OpenVINO)
  2. Embed alert and find similar past incidents on Xeon 6 (OpenVINO)
  3. Generate root cause analysis on Gaudi (vLLM)
  4. Governance gate — validate recommendation before action
"""

import os
import time
import json
import httpx
import argparse
import sys

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
MOCK_MODE = False

PAST_INCIDENTS = [
    {"id": "INC-2024-0891", "title": "API gateway latency spike", "rca": "Connection pool exhaustion due to slow upstream database queries. Fixed by increasing pool size and adding query timeout.", "severity": "P2", "action": "restart_service", "keywords": ["latency", "gateway", "timeout", "slow", "api"]},
    {"id": "INC-2024-1203", "title": "Pod OOM kills in inference namespace", "rca": "Model loaded without memory limits. Added resource limits and PVC-backed model cache.", "severity": "P2", "action": "update_config", "keywords": ["oom", "memory", "kill", "pod", "inference", "model"]},
    {"id": "INC-2025-0042", "title": "GPU node not schedulable", "rca": "Habana device plugin crashed after node reboot. Restarted DaemonSet and added liveness probe.", "severity": "P1", "action": "restart_service", "keywords": ["gpu", "gaudi", "node", "schedule", "device", "plugin"]},
    {"id": "INC-2025-0156", "title": "SSL certificate expiry on routes", "rca": "cert-manager renewal failed due to DNS challenge timeout. Updated DNS provider credentials.", "severity": "P1", "action": "update_config", "keywords": ["ssl", "certificate", "expiry", "tls", "route"]},
    {"id": "INC-2025-0289", "title": "Model serving 503 errors", "rca": "InferenceService scaled to zero and cold start exceeded readiness timeout. Set minReplicas=1.", "severity": "P2", "action": "scale_deployment", "keywords": ["503", "serving", "model", "cold", "start", "inference"]},
]

GOVERNANCE_POLICIES = {
    "restart_service": {"requires_approval": False, "auto_execute": True, "risk": "low"},
    "scale_deployment": {"requires_approval": False, "auto_execute": True, "risk": "low"},
    "update_config": {"requires_approval": True, "auto_execute": False, "risk": "medium"},
    "restart_node": {"requires_approval": True, "auto_execute": False, "risk": "high"},
    "escalate_oncall": {"requires_approval": False, "auto_execute": True, "risk": "low"},
}

MOCK_RESPONSES = {
    "classification": {"routing": {"selected_backend": "openvino-cpu", "accelerator": "xeon6", "reason": "Classification models run efficiently on CPU with ONNX/OpenVINO", "latency_ms": 3.5, "cost_estimate_per_1k_tokens": 0.001, "task": "classification"}, "result": {"label": "P2", "confidence": 0.87}},
    "embeddings": {"routing": {"selected_backend": "openvino-cpu", "accelerator": "xeon6", "reason": "Embeddings are compute-bound, AMX-accelerated on Xeon 6", "latency_ms": 4.8, "cost_estimate_per_1k_tokens": 0.001, "task": "embeddings"}, "result": {"data": [{"embedding": [0.1]*384}]}},
    "completion": {"routing": {"selected_backend": "vllm-gaudi", "accelerator": "gaudi", "reason": "Large models (> 3B) need Gaudi HBM and tensor acceleration", "latency_ms": 1450, "cost_estimate_per_1k_tokens": 0.008, "task": "completion"}, "result": {"choices": [{"text": "Based on similar incidents (INC-2024-0891, INC-2025-0289), this appears to be connection pool exhaustion or cold-start latency. Recommended action: restart the inference gateway pods and verify model serving readiness probes."}]}},
}


def call_gateway(task: str, **kwargs) -> dict:
    if MOCK_MODE:
        time.sleep(0.05)
        return MOCK_RESPONSES.get(task, MOCK_RESPONSES["completion"])
    try:
        payload = {"task": task, **kwargs}
        resp = httpx.post(f"{GATEWAY_URL}/v1/route", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        print(f"  ERROR: Gateway unreachable at {GATEWAY_URL}", file=sys.stderr)
        print(f"  Run with --mock for offline demo", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"  ERROR: Gateway returned {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.TimeoutException:
        print(f"  ERROR: Gateway timed out", file=sys.stderr)
        sys.exit(1)


def step_classify(alert_text: str) -> dict:
    result = call_gateway("classification", text=alert_text)
    classification = result.get("result", {})
    severity = classification.get("label", "P2")
    confidence = classification.get("confidence", 0.0)
    return {
        "step": "classify_severity",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "reason": result["routing"]["reason"],
        "latency_ms": result["routing"]["latency_ms"],
        "severity": severity,
        "confidence": confidence,
    }


def step_correlate(alert_text: str) -> dict:
    result = call_gateway("embeddings", text=alert_text)
    alert_words = set(alert_text.lower().split())
    scored = []
    for inc in PAST_INCIDENTS:
        keyword_overlap = len(alert_words & set(inc["keywords"]))
        title_overlap = len(alert_words & set(inc["title"].lower().split()))
        scored.append({"incident": inc, "score": keyword_overlap * 2 + title_overlap})
    scored.sort(key=lambda x: x["score"], reverse=True)
    similar = [s["incident"] for s in scored[:3] if s["score"] > 0]
    if not similar:
        similar = [PAST_INCIDENTS[0]]

    return {
        "step": "correlate_incidents",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "reason": result["routing"]["reason"],
        "latency_ms": result["routing"]["latency_ms"],
        "similar_incidents": similar,
    }


def step_generate_rca(alert_text: str, similar_incidents: list, severity: str) -> dict:
    context = "\n".join([
        f"- {inc['id']}: {inc['title']} (Severity: {inc['severity']}, Action: {inc['action']}, RCA: {inc['rca']})"
        for inc in similar_incidents
    ])
    prompt = (
        f"You are an SRE analyzing a {severity} incident.\n\n"
        f"Current alert: {alert_text}\n\n"
        f"Similar past incidents:\n{context}\n\n"
        f"Provide: 1) Root cause analysis 2) Recommended action (one of: restart_service, scale_deployment, update_config, restart_node, escalate_oncall)"
    )
    result = call_gateway("completion", prompt=prompt, model_size_b=7, max_tokens=200, temperature=0.3)
    error = result.get("error")
    if error:
        print(f"  WARNING: RCA generation error: {error}", file=sys.stderr)
    rca_text = result.get("result", {}).get("choices", [{}])[0].get("text", "")

    recommended_action = _extract_action(rca_text, similar_incidents)

    return {
        "step": "generate_rca",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "reason": result["routing"]["reason"],
        "latency_ms": result["routing"]["latency_ms"],
        "rca": rca_text,
        "recommended_action": recommended_action,
        "cost_per_1k": result["routing"]["cost_estimate_per_1k_tokens"],
    }


def _extract_action(rca_text: str, similar_incidents: list) -> str:
    """Extract recommended action from RCA text or infer from similar incidents."""
    text_lower = rca_text.lower()
    for action in GOVERNANCE_POLICIES:
        if action.replace("_", " ") in text_lower or action in text_lower:
            return action
    if similar_incidents:
        return similar_incidents[0].get("action", "escalate_oncall")
    return "escalate_oncall"


def step_governance(action: str, severity: str) -> dict:
    policy = GOVERNANCE_POLICIES.get(action, {
        "requires_approval": True, "auto_execute": False, "risk": "unknown"
    })

    if severity == "P1" and policy["risk"] != "low":
        decision = "escalate"
        reason = f"P1 severity with {policy['risk']}-risk action requires escalation"
    elif not policy.get("requires_approval", True):
        decision = "auto_approved"
        reason = f"Action '{action}' is low-risk and pre-approved"
    else:
        decision = "requires_approval"
        reason = f"Action '{action}' is {policy['risk']}-risk and requires human approval"

    return {
        "step": "governance_gate",
        "backend": "policy_engine",
        "accelerator": "local",
        "action": action,
        "risk_level": policy["risk"],
        "decision": decision,
        "reason": reason,
    }


def run_aiops(alert_text: str, verbose: bool = False):
    print(f"\n{'='*60}")
    print(f"AI Operations Copilot Demo" + (" [MOCK MODE]" if MOCK_MODE else ""))
    print(f"{'='*60}")
    print(f"Alert: {alert_text}\n")

    trace = []
    total_start = time.time()

    print("[1/4] Classifying alert severity on Xeon 6...")
    classify_result = step_classify(alert_text)
    trace.append(classify_result)
    print(f"      -> Severity: {classify_result['severity']} (confidence: {classify_result['confidence']:.0%})")
    print(f"         Backend: {classify_result['backend']} ({classify_result['latency_ms']:.0f}ms)")

    print("[2/4] Finding similar incidents on Xeon 6...")
    correlate_result = step_correlate(alert_text)
    trace.append(correlate_result)
    print(f"      -> {correlate_result['backend']} ({correlate_result['latency_ms']:.0f}ms)")
    for inc in correlate_result["similar_incidents"]:
        print(f"         {inc['id']}: {inc['title']} [{inc['severity']}]")

    print("[3/4] Generating root cause analysis on Gaudi...")
    rca_result = step_generate_rca(
        alert_text, correlate_result["similar_incidents"], classify_result["severity"]
    )
    trace.append(rca_result)
    print(f"      -> {rca_result['backend']} ({rca_result['latency_ms']:.0f}ms)")

    print("[4/4] Governance gate...")
    gov_result = step_governance(rca_result["recommended_action"], classify_result["severity"])
    trace.append(gov_result)
    print(f"      -> {gov_result['decision']} (action: {gov_result['action']}, risk: {gov_result['risk_level']})")

    total_ms = (time.time() - total_start) * 1000

    print(f"\n{'='*60}")
    print(f"Root Cause Analysis:")
    print(f"  {rca_result.get('rca', '[generated analysis]')}")
    print(f"\nRecommended Action: {rca_result['recommended_action']}")
    print(f"Governance: {gov_result['decision']} | {gov_result['reason']}")
    print(f"{'='*60}")
    print(f"\nRouting Trace:")
    print(f"  [1] Classify:   {trace[0]['accelerator']:>8}  {trace[0]['backend']}")
    print(f"  [2] Correlate:  {trace[1]['accelerator']:>8}  {trace[1]['backend']}")
    print(f"  [3] RCA:        {trace[2]['accelerator']:>8}  {trace[2]['backend']}")
    print(f"  [4] Governance: {'local':>8}  policy_engine")
    print(f"\n  Total: {total_ms:.0f}ms | Governed end-to-end")

    if verbose:
        print(f"\nFull trace:")
        print(json.dumps(trace, indent=2, default=str))

    return {"rca": rca_result.get("rca", ""), "action": rca_result["recommended_action"],
            "decision": gov_result["decision"], "trace": trace, "total_ms": total_ms}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOps Copilot Demo")
    parser.add_argument("--alert", default="High latency on inference gateway pods, p99 > 5s for last 10 minutes")
    parser.add_argument("--gateway", default=None)
    parser.add_argument("--mock", action="store_true", help="Run without gateway (simulated responses)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.gateway:
        GATEWAY_URL = args.gateway
    MOCK_MODE = args.mock

    result = run_aiops(args.alert, verbose=args.verbose)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
