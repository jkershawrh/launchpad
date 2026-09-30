"""RED/GREEN contract for the optional guided start inside an open sandbox."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
GUIDE = ROOT / "demos/containers/sandbox/guided-start.md"
RUNNER = ROOT / "demos/containers/sandbox/guided_start.py"
CONTAINERFILE = ROOT / "demos/containers/sandbox/Containerfile"
ENTRYPOINT = ROOT / "demos/containers/sandbox/entrypoint.sh"


def _runner_module():
    spec = importlib.util.spec_from_file_location("sandbox_guided_start", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_guide_tells_one_story_with_show_learn_do_prove_and_cleanup():
    text = GUIDE.read_text()

    assert "# Your first governed AI workload" in text
    for stage in ("## Show", "## Learn", "## Do", "## Prove", "## Clean up"):
        assert stage in text
    assert "launchpad-guided-start" in text
    assert "namespace" in text.lower()
    assert "model" in text.lower()
    assert "guided-start-proof.json" in text


def test_guided_workload_is_one_small_namespace_scoped_deployment():
    runner = _runner_module()

    manifests = runner.build_manifests(
        namespace="sandbox-seat-one",
        image="ghcr.io/example/sandbox@sha256:" + "a" * 64,
    )
    deployments = [item for item in manifests if item["kind"] == "Deployment"]

    assert len(deployments) == 1
    deployment = deployments[0]
    assert deployment["metadata"]["namespace"] == "sandbox-seat-one"
    assert deployment["spec"]["replicas"] == 1
    assert deployment["metadata"]["labels"]["launchpad.redhat.com/guided-start"] == "true"
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["resources"]["requests"] == {"cpu": "25m", "memory": "32Mi"}
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_model_probe_discovers_then_calls_an_available_model_without_leaking_key():
    runner = _runner_module()
    calls = []

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class Client:
        def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            return Response({"data": [{"id": "granite-test"}]})

        def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return Response(
                {
                    "model": "granite-test",
                    "choices": [{"message": {"content": "OpenShift keeps the seat scoped."}}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 7},
                }
            )

    result = runner.complete_model_probe(
        endpoint="https://maas.example.test",
        api_key="seat-secret",
        client=Client(),
    )

    assert result == {
        "status": "live",
        "model": "granite-test",
        "response": "OpenShift keeps the seat scoped.",
        "usage": {"prompt_tokens": 9, "completion_tokens": 7},
    }
    assert calls[0][0:2] == ("GET", "https://maas.example.test/v1/models")
    assert calls[1][0:2] == ("POST", "https://maas.example.test/v1/chat/completions")
    assert calls[0][2]["headers"] == {"Authorization": "Bearer seat-secret"}
    assert "seat-secret" not in json.dumps(result)


def test_model_probe_is_honest_when_endpoint_is_not_configured():
    runner = _runner_module()

    result = runner.complete_model_probe(endpoint="", api_key="", client=None)

    assert result["status"] == "unavailable"
    assert result["model"] is None
    assert "not configured" in result["reason"]


def test_container_packages_guide_and_runner_and_entrypoint_seeds_workspace_safely():
    containerfile = CONTAINERFILE.read_text()
    entrypoint = ENTRYPOINT.read_text()

    assert "COPY guided-start.md /opt/launchpad/guided-start.md" in containerfile
    assert "COPY guided_start.py /usr/local/bin/launchpad-guided-start" in containerfile
    assert "guided-start.md" in entrypoint
    assert "GETTING_STARTED.md" in entrypoint
    assert "if [[ ! -e" in entrypoint


def test_proof_writer_never_serializes_credentials(tmp_path):
    runner = _runner_module()
    proof_path = tmp_path / "guided-start-proof.json"

    runner.write_proof(
        proof_path,
        {
            "namespace": "sandbox-seat-one",
            "namespace_isolation": {"own_edit": True, "cross_namespace": False},
            "workload": {"status": "ready"},
            "model": {"status": "live", "model": "granite-test"},
            "cleanup": {"status": "complete"},
        },
    )

    rendered = proof_path.read_text()
    assert "sandbox-seat-one" in rendered
    assert "api_key" not in rendered.lower()
    assert "token" not in rendered.lower()


def test_proof_writer_allows_non_secret_token_counts(tmp_path):
    runner = _runner_module()
    proof_path = tmp_path / "guided-start-proof.json"

    runner.write_proof(
        proof_path,
        {
            "model": {
                "status": "live",
                "usage": {"prompt_tokens": 9, "completion_tokens": 7},
            }
        },
    )

    assert json.loads(proof_path.read_text())["model"]["usage"] == {
        "prompt_tokens": 9,
        "completion_tokens": 7,
    }
