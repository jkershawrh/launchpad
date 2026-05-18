"""Evidence recorder for Overdrive routing decisions."""

from dataclasses import asdict
from .models import Decision, InferenceRequest, Evidence


def record_decision(decision: Decision, request: InferenceRequest, route_states: dict) -> Evidence:
    return Evidence(decision=decision, request=request, route_states=route_states)


def evidence_to_dict(evidence: Evidence) -> dict:
    d = asdict(evidence.decision)
    d["request"] = asdict(evidence.request)
    d["route_states"] = evidence.route_states
    return d
