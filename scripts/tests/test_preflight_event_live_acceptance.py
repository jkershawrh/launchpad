from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "preflight_event_live_acceptance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("live_preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def _completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout, "")


def test_preflight_is_green_only_when_edge_identity_and_cluster_are_ready(
    monkeypatch,
):
    module = _load_module()
    origin = "https://labs.example.test"

    def get(url, **_kwargs):
        if url.endswith("/health"):
            return Response({"status": "ok"})
        return Response(
            {
                "issuer": f"{origin}/realms/launchpad-public",
                "authorization_endpoint": (
                    f"{origin}/realms/launchpad-public/protocol/openid-connect/auth"
                ),
                "token_endpoint": (
                    f"{origin}/realms/launchpad-public/protocol/openid-connect/token"
                ),
            }
        )

    deployments = {
        "items": [
            {
                "metadata": {"name": name},
                "spec": {"replicas": 2},
                "status": {"availableReplicas": 2},
            }
            for name in module.REQUIRED_DEPLOYMENTS
        ]
    }

    def oc(_kubeconfig, *args, **_kwargs):
        joined = " ".join(args)
        if "config view" in joined:
            return _completed("https://api.arena.example:6443")
        if args == ("whoami",):
            return _completed("redacted-user")
        if "auth can-i" in joined:
            return _completed("yes\n")
        return _completed(json.dumps(deployments))

    monkeypatch.setattr(module.requests, "get", get)
    monkeypatch.setattr(module, "_oc", oc)
    result = module.evaluate_preflight(
        public_origin=origin,
        kubeconfig=Path("/tmp/arena"),
        expected_api_server="https://api.arena.example:6443",
        namespace="partner-ai-launchpad",
    )

    assert result["ready_for_canary"] is True
    assert result["cluster_resources_mutated"] == 0
    assert "redacted-user" not in json.dumps(result)


def test_preflight_fails_closed_when_saved_cluster_credential_is_unauthorized(
    monkeypatch,
):
    module = _load_module()
    origin = "https://labs.example.test"
    discovery = {
        "issuer": f"{origin}/realms/launchpad-public",
        "authorization_endpoint": f"{origin}/realms/launchpad-public/auth",
        "token_endpoint": f"{origin}/realms/launchpad-public/token",
    }
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda url, **_kwargs: Response(
            {"status": "ok"} if url.endswith("/health") else discovery
        ),
    )

    def oc(_kubeconfig, *args, **_kwargs):
        if args[:2] == ("config", "view"):
            return _completed("https://api.arena.example:6443")
        return _completed(returncode=1)

    monkeypatch.setattr(module, "_oc", oc)
    result = module.evaluate_preflight(
        public_origin=origin,
        kubeconfig=Path("/tmp/arena"),
        expected_api_server="https://api.arena.example:6443",
        namespace="partner-ai-launchpad",
    )

    assert result["ready_for_canary"] is False
    assert result["checks"]["cluster_authentication"] == {
        "passed": False,
        "error_type": "unauthorized",
    }
    assert result["checks"]["required_deployments"]["passed"] is False
    assert result["cluster_resources_mutated"] == 0
