#!/usr/bin/env python3
"""Regression tests — existing demo routing still works after Overdrive Lite."""

import subprocess
import pytest
from pathlib import Path


class TestExistingRouterUnchanged:
    def test_routing_policy_compiles(self, project_root):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(project_root / "gateway" / "routing_policy.py")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"routing_policy.py broken: {result.stderr}"

    def test_router_compiles(self, project_root):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(project_root / "gateway" / "router.py")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"router.py broken: {result.stderr}"

    def test_existing_config_loads(self, project_root):
        import yaml
        config = yaml.safe_load((project_root / "gateway" / "config.yaml").read_text())
        assert "backends" in config
        assert "routes" in config

    def test_existing_routing_still_works(self, project_root):
        import sys
        gw = str(project_root / "gateway")
        sys.path.insert(0, gw)
        try:
            import importlib
            import routing_policy as rp
            importlib.reload(rp)
            config = __import__("yaml").safe_load((project_root / "gateway" / "config.yaml").read_text())
            policy = rp.RoutingPolicy(config)
            decision = policy.route("embeddings")
            assert decision.backend == "openvino-cpu"
            decision = policy.route("completion", model_size_b=1)
            assert decision.backend == "vllm-cpu"
        finally:
            sys.path.remove(gw)


class TestOverdriveDoesNotBreakExisting:
    def test_overdrive_module_imports(self, project_root):
        import sys
        gw = str(project_root / "gateway")
        sys.path.insert(0, gw)
        try:
            import overdrive.engine
            import overdrive.models
            import overdrive.matrix
            import overdrive.rubric
            import overdrive.evidence
            import overdrive.report
        finally:
            sys.path.remove(gw)

    def test_overdrive_does_not_modify_routing_policy(self, project_root):
        content = (project_root / "gateway" / "routing_policy.py").read_text()
        assert "overdrive" not in content.lower(), \
            "routing_policy.py should not reference overdrive"

    def test_overdrive_endpoints_coexist_with_existing(self, project_root):
        content = (project_root / "gateway" / "router.py").read_text()
        assert "/v1/route" in content, "Existing /v1/route endpoint must still exist"
        assert "/v1/overdrive/route" in content, "Overdrive endpoints should be present"
        assert "OverdriveEngine" in content, "OverdriveEngine should be imported"
