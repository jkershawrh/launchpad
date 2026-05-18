#!/usr/bin/env python3
"""Rubric loader and evaluator for StarGate Overdrive Lite routing.

Loads route rubrics from YAML and evaluates inference requests against
route capabilities to produce pass/fail/warn check results.
"""

from pathlib import Path
from typing import Dict, List

import yaml

try:
    from .models import Check, InferenceRequest, Route
except ImportError:
    from overdrive.models import Check, InferenceRequest, Route


# ---------------------------------------------------------------------------
# Rubric loader
# ---------------------------------------------------------------------------

def load_rubrics(rubric_dir: Path) -> Dict[str, dict]:
    """Load all YAML rubric files from *rubric_dir*, keyed by route_id."""
    rubrics: Dict[str, dict] = {}
    for path in sorted(rubric_dir.glob("*.yaml")):
        with open(path) as fh:
            data = yaml.safe_load(fh)
        route_id = data["route_id"]
        rubrics[route_id] = data
    return rubrics


# ---------------------------------------------------------------------------
# Individual check evaluators
# ---------------------------------------------------------------------------

_OVERDRIVE_TOKEN_THRESHOLD = 16000
_OVERDRIVE_PRIORITIES = {"high", "critical"}


def _check_endpoint_defined(req: InferenceRequest, route: Route) -> Check:
    passed = bool(route.target_endpoint)
    return Check(
        name="endpoint_defined",
        route=route.route_id,
        result="pass" if passed else "fail",
        observed=route.target_endpoint or "(empty)",
        reason=f"Endpoint '{route.target_endpoint}' is configured" if passed else "No endpoint configured for this lane",
    )


def _check_endpoint_health_pass(req: InferenceRequest, route: Route) -> Check:
    return Check(
        name="endpoint_health_pass",
        route=route.route_id,
        result="pass" if route.healthy else "fail",
        observed=route.healthy,
        reason=f"Lane {route.route_id} is healthy and accepting requests" if route.healthy else f"Lane {route.route_id} is marked unhealthy — will not receive traffic",
    )


def _check_supports_task_type(req: InferenceRequest, route: Route) -> Check:
    passed = req.task_type in route.capabilities
    return Check(
        name="supports_task_type",
        route=route.route_id,
        result="pass" if passed else "fail",
        observed=f"{req.task_type} (lane supports: {', '.join(route.capabilities)})",
        reason=f"Task '{req.task_type}' is in lane capabilities" if passed else f"Task '{req.task_type}' not supported — lane only handles: {', '.join(route.capabilities)}",
    )


def _check_token_estimate_within_limit(req: InferenceRequest, route: Route) -> Check:
    passed = req.token_estimate <= route.max_token_estimate
    return Check(
        name="token_estimate_within_limit",
        route=route.route_id,
        result="pass" if passed else "fail",
        observed=f"{req.token_estimate:,} tokens (limit: {route.max_token_estimate:,})",
        reason=f"{req.token_estimate:,} tokens within lane limit of {route.max_token_estimate:,}" if passed else f"{req.token_estimate:,} tokens exceeds lane max of {route.max_token_estimate:,}",
    )


def _check_latency_target_supported(req: InferenceRequest, route: Route) -> Check:
    return Check(
        name="latency_target_supported",
        route=route.route_id,
        result="pass",
        observed=f"{req.latency_target_ms:,}ms target",
        reason=f"Latency target of {req.latency_target_ms:,}ms is achievable on this lane",
    )


def _check_supports_heavy_generation(req: InferenceRequest, route: Route) -> Check:
    passed = req.task_type in route.capabilities
    return Check(
        name="supports_heavy_generation",
        route=route.route_id,
        result="pass" if passed else "fail",
        observed=f"{req.task_type} (lane supports: {', '.join(route.capabilities)})",
        reason=f"Heavy generation task '{req.task_type}' is supported" if passed else f"Task '{req.task_type}' not available on this accelerator lane",
    )


def _check_token_estimate_requires_overdrive(req: InferenceRequest, route: Route) -> Check:
    passed = req.token_estimate >= _OVERDRIVE_TOKEN_THRESHOLD
    return Check(
        name="token_estimate_requires_overdrive",
        route=route.route_id,
        result="pass" if passed else "fail",
        observed=f"{req.token_estimate:,} tokens (threshold: {_OVERDRIVE_TOKEN_THRESHOLD:,})",
        reason=f"{req.token_estimate:,} tokens requires overdrive tier (>= {_OVERDRIVE_TOKEN_THRESHOLD:,})" if passed else f"{req.token_estimate:,} tokens too small for overdrive — threshold is {_OVERDRIVE_TOKEN_THRESHOLD:,}",
    )


def _check_priority_allows_overdrive(req: InferenceRequest, route: Route) -> Check:
    passed = req.priority in _OVERDRIVE_PRIORITIES
    return Check(
        name="priority_allows_overdrive",
        route=route.route_id,
        result="pass" if passed else "fail",
        observed=f"{req.priority} (required: {', '.join(sorted(_OVERDRIVE_PRIORITIES))})",
        reason=f"Priority '{req.priority}' qualifies for overdrive tier" if passed else f"Priority '{req.priority}' too low — overdrive requires {', '.join(sorted(_OVERDRIVE_PRIORITIES))}",
    )


def _check_latency_target_requires_or_allows_overdrive(
    req: InferenceRequest, route: Route,
) -> Check:
    return Check(
        name="latency_target_requires_or_allows_overdrive",
        route=route.route_id,
        result="pass",
        observed=f"{req.latency_target_ms:,}ms target",
        reason=f"Latency target of {req.latency_target_ms:,}ms is compatible with overdrive lane",
    )


# ---------------------------------------------------------------------------
# Check dispatcher
# ---------------------------------------------------------------------------

_CHECK_DISPATCH = {
    "endpoint_defined": _check_endpoint_defined,
    "endpoint_health_pass": _check_endpoint_health_pass,
    "supports_task_type": _check_supports_task_type,
    "token_estimate_within_limit": _check_token_estimate_within_limit,
    "latency_target_supported": _check_latency_target_supported,
    "supports_heavy_generation": _check_supports_heavy_generation,
    "token_estimate_requires_overdrive": _check_token_estimate_requires_overdrive,
    "priority_allows_overdrive": _check_priority_allows_overdrive,
    "latency_target_requires_or_allows_overdrive": _check_latency_target_requires_or_allows_overdrive,
}


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate_route(
    request: InferenceRequest,
    route: Route,
    rubric: dict,
) -> List[Check]:
    """Run each required check from *rubric* against *request*/*route*.

    Returns a list of :class:`Check` objects with pass/fail/warn results.
    """
    checks: List[Check] = []
    for check_name in rubric.get("required_checks", []):
        evaluator = _CHECK_DISPATCH.get(check_name)
        if evaluator is None:
            checks.append(Check(
                name=check_name,
                route=route.route_id,
                result="fail",
                reason=f"unknown check '{check_name}'",
            ))
        else:
            checks.append(evaluator(request, route))
    return checks


def route_passes(checks: List[Check]) -> bool:
    """Return True if no check has result ``'fail'``."""
    return all(c.result != "fail" for c in checks)


def route_warns(checks: List[Check]) -> bool:
    """Return True if any check has result ``'warn'``."""
    return any(c.result == "warn" for c in checks)
