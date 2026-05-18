#!/usr/bin/env python3
"""
Governed Agent Execution Demo — Intel-Red Hat AI Partner Platform

Demonstrates that AI agents need more than inference — they need
governed execution with evidence, policy checks, and audit trails:

  1. Classify intent on Xeon 6 (OpenVINO) — what is the agent trying to do?
  2. Risk score on Xeon 6 (OpenVINO) — how dangerous is this action?
  3. Generate execution plan on Gaudi (vLLM) — reasoning and planning
  4. Policy validation — is this allowed?
  5. Decision: allow / deny / escalate — with evidence bundle
"""

import os
import time
import json
import httpx
import argparse
import sys
from datetime import datetime

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
MOCK_MODE = False

ACTION_KEYWORDS = {
    "read_logs": ["log", "read", "view", "check", "inspect", "describe", "get"],
    "restart_pod": ["restart", "bounce", "recycle", "kill pod"],
    "scale_deployment": ["scale", "replica", "autoscal"],
    "update_configmap": ["update", "change", "modify", "configmap", "config", "edit", "set"],
    "delete_namespace": ["delete", "remove", "destroy", "namespace", "drop"],
    "modify_rbac": ["rbac", "role", "permission", "clusterrole", "rolebinding"],
    "patch_deployment": ["patch", "deploy", "image", "container", "rollout"],
    "create_network_policy": ["network", "policy", "firewall", "ingress", "egress"],
}

POLICY_RULES = {
    "read_logs": {"allowed": True, "risk": "low", "base_score": 0.1},
    "restart_pod": {"allowed": True, "risk": "medium", "base_score": 0.4},
    "scale_deployment": {"allowed": True, "risk": "medium", "base_score": 0.35},
    "update_configmap": {"allowed": True, "risk": "medium", "base_score": 0.5},
    "delete_namespace": {"allowed": False, "risk": "critical", "base_score": 0.95},
    "modify_rbac": {"allowed": False, "risk": "critical", "base_score": 0.95},
    "patch_deployment": {"allowed": True, "risk": "high", "base_score": 0.7},
    "create_network_policy": {"allowed": True, "risk": "high", "base_score": 0.65},
}

RISK_AMPLIFIERS = {
    "production": 0.2, "prod": 0.2,
    "critical": 0.15, "important": 0.1,
    "all": 0.1, "every": 0.1,
    "privileged": 0.25, "root": 0.2,
    "secret": 0.15, "credential": 0.15,
}

MOCK_RESPONSES = {
    "classification": {"routing": {"selected_backend": "openvino-cpu", "accelerator": "xeon6", "reason": "Classification models run efficiently on CPU with ONNX/OpenVINO", "latency_ms": 3.2, "cost_estimate_per_1k_tokens": 0.001, "task": "classification"}, "result": {"label": "restart_pod", "confidence": 0.82}},
    "completion": {"routing": {"selected_backend": "vllm-gaudi", "accelerator": "gaudi", "reason": "Large models (> 3B) need Gaudi HBM and tensor acceleration", "latency_ms": 980, "cost_estimate_per_1k_tokens": 0.008, "task": "completion"}, "result": {"choices": [{"text": "1. Cordon the affected node to prevent new pods scheduling\n2. Identify the OOM-killed pods with oc get pods --field-selector=status.phase=Failed\n3. Delete the failed pods: oc delete pod <name>\n4. Verify new pods start with correct memory limits\n5. Uncordon the node\n\nRollback: If new pods also OOM, revert to previous deployment revision with oc rollout undo"}]}},
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


def _classify_intent_from_text(request_text: str) -> tuple:
    """Classify intent using keyword matching as model-output simulation."""
    text_lower = request_text.lower()
    best_action = "patch_deployment"
    best_score = 0
    for action, keywords in ACTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_action = action
    confidence = min(0.95, 0.5 + best_score * 0.15)
    return best_action, confidence


def step_classify_intent(request_text: str) -> dict:
    result = call_gateway("classification", text=request_text)
    classification = result.get("result", {})

    if classification and classification.get("label") in POLICY_RULES:
        intent = classification["label"]
        confidence = classification.get("confidence", 0.8)
    else:
        intent, confidence = _classify_intent_from_text(request_text)

    return {
        "step": "classify_intent",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "latency_ms": result["routing"]["latency_ms"],
        "intent": intent,
        "confidence": confidence,
    }


def step_risk_score(intent: str, request_text: str) -> dict:
    result = call_gateway("classification", text=f"Risk assessment: {request_text}")

    rule = POLICY_RULES.get(intent, {"risk": "high", "base_score": 0.8})
    risk_score = rule["base_score"]

    text_lower = request_text.lower()
    for trigger, amplifier in RISK_AMPLIFIERS.items():
        if trigger in text_lower:
            risk_score = min(1.0, risk_score + amplifier)

    if risk_score <= 0.3:
        risk_level = "low"
    elif risk_score <= 0.6:
        risk_level = "medium"
    elif risk_score <= 0.85:
        risk_level = "high"
    else:
        risk_level = "critical"

    return {
        "step": "risk_score",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "latency_ms": result["routing"]["latency_ms"],
        "risk_level": risk_level,
        "risk_score": round(risk_score, 2),
        "amplifiers_triggered": [k for k in RISK_AMPLIFIERS if k in text_lower],
    }


def step_plan(request_text: str, intent: str, risk_level: str) -> dict:
    prompt = (
        f"You are an operations agent planning an action.\n\n"
        f"Request: {request_text}\n"
        f"Classified intent: {intent}\n"
        f"Risk level: {risk_level}\n\n"
        f"Generate a safe execution plan with numbered steps and a rollback procedure."
    )
    result = call_gateway("completion", prompt=prompt, model_size_b=7, max_tokens=200, temperature=0.2)
    error = result.get("error")
    if error:
        print(f"  WARNING: Plan generation error: {error}", file=sys.stderr)
    plan = result.get("result", {}).get("choices", [{}])[0].get("text", "")
    return {
        "step": "generate_plan",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "latency_ms": result["routing"]["latency_ms"],
        "plan": plan,
        "cost_per_1k": result["routing"]["cost_estimate_per_1k_tokens"],
    }


def step_policy_check(intent: str, risk_score: float, request_text: str) -> dict:
    rule = POLICY_RULES.get(intent, {"allowed": False, "risk": "critical"})

    if not rule["allowed"]:
        decision = "deny"
        reason = f"Action '{intent}' is explicitly prohibited by policy"
    elif risk_score > 0.7:
        decision = "escalate"
        reason = f"Risk score {risk_score:.2f} exceeds auto-approval threshold (0.7)"
    elif risk_score > 0.3:
        decision = "allow_with_audit"
        reason = f"Risk score {risk_score:.2f} — approved with mandatory audit trail"
    else:
        decision = "allow"
        reason = f"Risk score {risk_score:.2f} — within auto-approval range"

    return {
        "step": "policy_check",
        "backend": "policy_engine",
        "accelerator": "local",
        "decision": decision,
        "reason": reason,
        "requires_human": decision in ("deny", "escalate"),
        "evidence": {
            "request": request_text,
            "intent": intent,
            "risk_score": risk_score,
            "policy_rule": rule,
            "decision": decision,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    }


def run_governed_agent(request_text: str, verbose: bool = False):
    print(f"\n{'='*60}")
    print(f"Governed Agent Execution Demo" + (" [MOCK MODE]" if MOCK_MODE else ""))
    print(f"{'='*60}")
    print(f"Request: {request_text}\n")

    trace = []
    total_start = time.time()

    print("[1/4] Classifying intent on Xeon 6...")
    intent_result = step_classify_intent(request_text)
    trace.append(intent_result)
    print(f"      -> Intent: {intent_result['intent']} (confidence: {intent_result['confidence']:.0%})")
    print(f"         Backend: {intent_result['backend']} ({intent_result['latency_ms']:.0f}ms)")

    print("[2/4] Scoring risk on Xeon 6...")
    risk_result = step_risk_score(intent_result["intent"], request_text)
    trace.append(risk_result)
    print(f"      -> Risk: {risk_result['risk_level']} (score: {risk_result['risk_score']:.2f})")
    if risk_result.get("amplifiers_triggered"):
        print(f"         Amplifiers: {', '.join(risk_result['amplifiers_triggered'])}")
    print(f"         Backend: {risk_result['backend']} ({risk_result['latency_ms']:.0f}ms)")

    print("[3/4] Planning execution on Gaudi...")
    plan_result = step_plan(request_text, intent_result["intent"], risk_result["risk_level"])
    trace.append(plan_result)
    print(f"      -> Backend: {plan_result['backend']} ({plan_result['latency_ms']:.0f}ms)")

    print("[4/4] Policy validation...")
    policy_result = step_policy_check(intent_result["intent"], risk_result["risk_score"], request_text)
    trace.append(policy_result)

    total_ms = (time.time() - total_start) * 1000

    decision_display = {
        "allow": "ALLOWED",
        "allow_with_audit": "ALLOWED (audit required)",
        "escalate": "ESCALATED (human review required)",
        "deny": "DENIED",
    }

    print(f"\n{'='*60}")
    print(f"Decision: {decision_display.get(policy_result['decision'], policy_result['decision'])}")
    print(f"Reason:   {policy_result['reason']}")
    if plan_result.get("plan"):
        print(f"\nExecution Plan:")
        for line in plan_result["plan"].strip().split("\n"):
            print(f"  {line}")
    print(f"{'='*60}")
    print(f"\nRouting Trace:")
    print(f"  [1] Intent:     {trace[0]['accelerator']:>8}  {trace[0]['backend']}")
    print(f"  [2] Risk:       {trace[1]['accelerator']:>8}  {trace[1]['backend']}")
    print(f"  [3] Plan:       {trace[2]['accelerator']:>8}  {trace[2]['backend']}")
    print(f"  [4] Policy:     {'local':>8}  policy_engine")
    print(f"\n  Total: {total_ms:.0f}ms | Decision: {policy_result['decision']}")
    print(f"  Human required: {'YES' if policy_result['requires_human'] else 'no'}")

    if verbose:
        print(f"\nEvidence bundle:")
        print(json.dumps(policy_result["evidence"], indent=2, default=str))

    return {"decision": policy_result["decision"], "intent": intent_result["intent"],
            "risk_score": risk_result["risk_score"], "trace": trace, "total_ms": total_ms}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Governed Agent Execution Demo")
    parser.add_argument("--request", default="Restart the inference pods in the gaudi namespace to clear the OOM state")
    parser.add_argument("--gateway", default=None)
    parser.add_argument("--mock", action="store_true", help="Run without gateway (simulated responses)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.gateway:
        GATEWAY_URL = args.gateway
    MOCK_MODE = args.mock

    result = run_governed_agent(args.request, verbose=args.verbose)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
