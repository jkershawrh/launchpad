#!/usr/bin/env python3
"""StarGate Overdrive Lite data models."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InferenceRequest:
    """Represents an incoming inference request to be routed."""

    request_id: str
    task_type: str
    priority: str
    token_estimate: int
    latency_target_ms: int
    prompt: str = ""
    modality: str = "text"
    image_ref: str = ""
    document_ref: str = ""
    image_count: int = 0
    page_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Route:
    """Represents a routing lane/endpoint that can serve inference requests."""

    route_id: str
    lane: str
    target_endpoint: str
    capabilities: List[str] = field(default_factory=list)
    max_token_estimate: int = 0
    healthy: bool = True
    current_load: float = 0.0
    model: str = ""
    accelerator: str = ""


@dataclass
class Check:
    """Represents a single evaluation check performed during routing."""

    name: str
    route: str
    result: str  # "pass", "fail", or "warn"
    observed: Any = None
    reason: Optional[str] = None


@dataclass
class Decision:
    """Represents the final routing decision for a request."""

    decision_id: str
    request_id: str
    outcome: str  # "route", "fallback", or "indeterminate"
    selected_route: Optional[str]
    evaluated_routes: List[str] = field(default_factory=list)
    checks: List[Check] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class Evidence:
    """Bundles a decision with the request and route state for audit/debug."""

    decision: Decision
    request: InferenceRequest
    route_states: Dict[str, Any] = field(default_factory=dict)
