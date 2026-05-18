#!/usr/bin/env python3
"""
Overdrive routing matrix — config loader and lane matcher.

Loads the routing config from config.yaml and provides functions
to match incoming requests to the appropriate lane, with fallback
support.
"""

import os
import re
from pathlib import Path
from typing import Optional

import yaml


_ENV_PATTERN = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


def _resolve_env_vars(value):
    """Recursively resolve ${VAR} and ${VAR:-default} patterns in config values."""
    if isinstance(value, str):
        def _replacer(match):
            env_var = match.group(1)
            default = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(env_var, default)
        return _ENV_PATTERN.sub(_replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config(path: Path) -> dict:
    """Load and validate the routing matrix YAML config.

    Args:
        path: Path to the config.yaml file.

    Returns:
        Parsed and validated config dict with env vars resolved.

    Raises:
        ValueError: If the config is missing required top-level keys.
    """
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    required_keys = {"lanes", "routing_matrix", "fallback_rules"}
    missing = required_keys - set(config.keys())
    if missing:
        raise ValueError(f"Config missing required keys: {missing}")

    config = _resolve_env_vars(config)
    return config


def match_lane(
    task_type: str,
    token_estimate: int,
    priority: str,
    latency_target_ms: int,
    config: dict,
) -> Optional[str]:
    """Match a request to a lane using the routing matrix.

    Iterates routing_matrix entries in order. Returns the lane name
    of the first matching rule, or None if no rule matches.

    Args:
        task_type: The type of task (e.g. "classification", "embedding").
        token_estimate: Estimated token count for the request.
        priority: Request priority ("low", "normal", "high", "critical").
        latency_target_ms: Maximum acceptable latency in milliseconds.
        config: Loaded config dict from load_config().

    Returns:
        Lane name string, or None if no rule matches.
    """
    for rule in config["routing_matrix"]:
        # Task type must match exactly
        if rule["task_type"] != task_type:
            continue

        # Check token_max bound (if present)
        if "token_max" in rule and token_estimate > rule["token_max"]:
            continue

        # Check token_min bound (if present)
        if "token_min" in rule and token_estimate < rule["token_min"]:
            continue

        # Check priority
        rule_priority = rule.get("priority", "any")
        if rule_priority != "any":
            if isinstance(rule_priority, list):
                if priority not in rule_priority:
                    continue
            elif rule_priority != priority:
                continue

        # Check latency target
        if "latency_target_max" in rule:
            if latency_target_ms > rule["latency_target_max"]:
                continue

        return rule["lane"]

    return None


def _evaluate_condition(
    condition: str, task_type: str, token_estimate: int
) -> bool:
    """Evaluate a fallback condition string.

    Supports two patterns:
      - token_estimate_lt_<N>: True if token_estimate < N
      - task_type_in_<type1>_<type2>_...: True if task_type is in the list

    Args:
        condition: Condition string from fallback_rules.
        task_type: The task type of the current request.
        token_estimate: The token estimate of the current request.

    Returns:
        True if the condition is met.
    """
    if condition.startswith("token_estimate_lt_"):
        threshold = int(condition.split("token_estimate_lt_")[1])
        return token_estimate < threshold

    if condition.startswith("task_type_in_"):
        suffix = condition.split("task_type_in_")[1]
        # Support comma-separated (preferred) and underscore-separated values
        if "," in suffix:
            allowed_types = [t.strip() for t in suffix.split(",")]
        else:
            allowed_types = suffix.split("_")
        return task_type in allowed_types

    return False


def get_fallback(
    lane: str,
    task_type: str,
    token_estimate: int,
    config: dict,
) -> Optional[str]:
    """Determine the fallback lane for a given lane and request.

    Iterates fallback_rules, matches the 'from' lane, and evaluates
    the condition. Returns the 'to' lane of the first matching rule,
    or None if no fallback applies.

    Args:
        lane: The current lane name that needs a fallback.
        task_type: The task type of the current request.
        token_estimate: The token estimate of the current request.
        config: Loaded config dict from load_config().

    Returns:
        Fallback lane name string, or None if no fallback applies.
    """
    for rule in config["fallback_rules"]:
        if rule["from"] != lane:
            continue

        if _evaluate_condition(rule["condition"], task_type, token_estimate):
            return rule["to"]

    return None
