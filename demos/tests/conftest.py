#!/usr/bin/env python3
"""
Shared pytest fixtures for all test modules

This file is automatically loaded by pytest and makes fixtures
available to all test files.
"""

import pytest
from pathlib import Path


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory"""
    # tests/conftest.py -> tests/ -> project_root/
    return Path(__file__).parent.parent


def parse_k8s_memory_gi(memory_str: str) -> float:
    """Parse Kubernetes memory string to GiB float"""
    if memory_str.endswith("Gi"):
        return float(memory_str[:-2])
    elif memory_str.endswith("Mi"):
        return float(memory_str[:-2]) / 1024
    elif memory_str.endswith("Ti"):
        return float(memory_str[:-2]) * 1024
    raise ValueError(f"Unknown memory format: {memory_str}")
