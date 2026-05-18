"""
Inference Routing Policy Engine

Decides which backend handles each inference request based on:
- Task type (embeddings, classification, completion, etc.)
- Model size
- Backend capabilities and availability
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", str(Path(__file__).parent / "config.yaml")))


@dataclass
class RoutingDecision:
    backend: str
    reason: str
    task: str
    fallback: Optional[str] = None


@dataclass
class BackendInfo:
    name: str
    url: str
    accelerator: str
    capabilities: list = field(default_factory=list)
    cost_per_1k_tokens: float = 0.0
    max_concurrent: int = 10
    healthy: bool = True
    api_key: str = ""


def _resolve_env(value: str) -> str:
    """Replace ${ENV_VAR} references with environment variable values."""
    if not isinstance(value, str):
        return value
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), value)


class RoutingPolicy:
    def __init__(self, config: dict):
        if not config:
            raise ValueError("Routing config is empty")

        raw_backends = config.get('backends', [])
        if not raw_backends:
            raise ValueError("No backends defined in routing config")

        self.backends = {}
        for b in raw_backends:
            for required in ('name', 'url', 'capabilities', 'accelerator'):
                if required not in b:
                    raise ValueError(f"Backend missing required field '{required}': {b}")
            resolved = {k: _resolve_env(v) if isinstance(v, str) else v for k, v in b.items()}
            if not resolved.get('url'):
                logger.warning("Backend '%s' has empty URL (env var not set?), skipping", b['name'])
                continue
            self.backends[resolved['name']] = BackendInfo(**{
                k: v for k, v in resolved.items()
                if k in BackendInfo.__dataclass_fields__
            })

        self.routes = config.get('routes', [])
        if not self.routes:
            logger.warning("No routes defined in routing config")

        for route in self.routes:
            if 'task' not in route:
                raise ValueError(f"Route missing 'task' field: {route}")
            if 'backend' not in route and 'conditions' not in route:
                raise ValueError(f"Route for '{route['task']}' needs 'backend' or 'conditions'")

    def route(self, task: str, model_size_b: float = 0, **kwargs) -> RoutingDecision:
        if model_size_b < 0:
            model_size_b = 0

        matching = [r for r in self.routes if r['task'] == task]
        if not matching:
            return RoutingDecision(
                backend="vllm-cpu",
                reason=f"No route defined for task '{task}', defaulting to CPU",
                task=task,
            )

        rule = matching[0]

        if 'conditions' in rule:
            for cond in rule['conditions']:
                threshold = cond.get('model_size_b', 0)
                op = cond.get('operator', '<=')
                backend = cond.get('backend')
                if not backend:
                    continue
                matched = False
                if op == '<=' and model_size_b <= threshold:
                    matched = True
                elif op == '>' and model_size_b > threshold:
                    matched = True
                elif op == '<' and model_size_b < threshold:
                    matched = True
                elif op == '>=' and model_size_b >= threshold:
                    matched = True
                elif op == '==' and model_size_b == threshold:
                    matched = True
                if matched:
                    return RoutingDecision(
                        backend=backend,
                        reason=cond.get('reason', rule.get('reason', '')),
                        task=task,
                        fallback=rule.get('fallback'),
                    )
            return RoutingDecision(
                backend=rule.get('default_backend', 'vllm-cpu'),
                reason=rule.get('reason', 'Default fallback'),
                task=task,
                fallback=rule.get('fallback'),
            )

        return RoutingDecision(
            backend=rule['backend'],
            reason=rule.get('reason', ''),
            task=task,
            fallback=rule.get('fallback'),
        )

    def get_backend(self, name: str) -> Optional[BackendInfo]:
        return self.backends.get(name)

    def list_backends(self) -> list:
        return list(self.backends.values())

    def list_routes(self) -> list:
        return self.routes


def load_config(path: Optional[Path] = None) -> dict:
    config_path = path or CONFIG_PATH
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Routing config not found: {config_path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML in routing config {config_path}: {e}")
    if not config:
        raise RuntimeError(f"Routing config is empty: {config_path}")
    return config
