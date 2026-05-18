#!/usr/bin/env python3
"""
Shared test helpers (importable from any test module).
"""


def parse_k8s_memory_gi(memory_str: str) -> float:
    """Parse Kubernetes memory string to GiB float"""
    if memory_str.endswith("Gi"):
        return float(memory_str[:-2])
    elif memory_str.endswith("Mi"):
        return float(memory_str[:-2]) / 1024
    elif memory_str.endswith("Ti"):
        return float(memory_str[:-2]) * 1024
    raise ValueError(f"Unknown memory format: {memory_str}")
