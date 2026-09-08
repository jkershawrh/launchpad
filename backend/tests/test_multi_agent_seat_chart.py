from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy/workloads/multi-agent-seat"
BUILD_CONFIG = ROOT / "deploy/launchpad/overlays/arena/buildconfig.yaml"

SOURCE_REPOSITORY = "https://github.com/jkershawrh/multi-agent-quickstart.git"
SOURCE_REVISION = "8a8e0241265e69be81bf28060c4a96be38d5c244"
IMAGE_REPOSITORY = (
    "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/"
    "multi-agent-quickstart"
)
TEST_DIGEST = "sha256:" + ("a" * 64)

OWNERSHIP_LABELS = {
    "app.kubernetes.io/managed-by": "launchpad",
    "launchpad.redhat.com/session-id": "session-1",
    "launchpad.redhat.com/workshop-id": "workshop-1",
    "launchpad.redhat.com/seat-id": "seat-1",
    "launchpad.redhat.com/tenant": "tenant-1",
    "launchpad.redhat.com/cluster-id": "arena",
}

IDENTITY_ARGS = [
    "--set",
    "identity.sessionId=session-1",
    "--set",
    "identity.workshopId=workshop-1",
    "--set",
    "identity.seatId=seat-1",
    "--set",
    "identity.tenantId=tenant-1",
    "--set",
    "identity.clusterId=arena",
]


def _render(
    namespace: str = "launchpad-cert-multi-agent-123456",
) -> tuple[str, list[dict[str, Any]]]:
    completed = subprocess.run(
        [
            "helm",
            "template",
            "multi-agent",
            str(CHART),
            "--namespace",
            namespace,
            "--set",
            "runtime.existingSecret=multi-agent-runtime",
            "--set",
            f"image.repository={IMAGE_REPOSITORY}",
            "--set",
            f"image.digest={TEST_DIGEST}",
            *IDENTITY_ARGS,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    documents = [document for document in yaml.safe_load_all(completed.stdout) if document]
    return completed.stdout, documents


def _env(container: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in container.get("env", [])}


def test_multi_agent_chart_starts_red_without_runtime_identity_or_digest():
    for arguments, expected in (
        (
            ["--set", f"image.digest={TEST_DIGEST}", *IDENTITY_ARGS],
            "runtime.existingSecret",
        ),
        (
            [
                "--set",
                "runtime.existingSecret=multi-agent-runtime",
                *IDENTITY_ARGS,
            ],
            "image.digest",
        ),
        (
            [
                "--set",
                "runtime.existingSecret=multi-agent-runtime",
                "--set",
                f"image.digest={TEST_DIGEST}",
            ],
            "identity.sessionId",
        ),
    ):
        completed = subprocess.run(
            ["helm", "template", "multi-agent", str(CHART), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0
        assert expected in completed.stderr


def test_multi_agent_chart_is_secret_free_namespace_scoped_and_fully_owned():
    rendered, documents = _render()

    forbidden = {
        "ClusterRole",
        "ClusterRoleBinding",
        "ConsoleLink",
        "Namespace",
        "OperatorGroup",
        "Secret",
        "Subscription",
    }
    assert documents
    assert not ({document["kind"] for document in documents} & forbidden)
    assert "sk-" not in rendered
    assert ":latest" not in rendered

    for document in documents:
        labels = document.get("metadata", {}).get("labels", {})
        assert labels.items() >= OWNERSHIP_LABELS.items(), (
            document["kind"],
            document["metadata"]["name"],
        )


def test_multi_agent_chart_uses_one_pod_for_the_complete_participant_runtime():
    _, documents = _render()
    deployments = [item for item in documents if item["kind"] == "Deployment"]
    assert [item["metadata"]["name"] for item in deployments] == ["multi-agent"]

    deployment = deployments[0]
    pod_spec = deployment["spec"]["template"]["spec"]
    containers = {item["name"]: item for item in pod_spec["containers"]}
    assert set(containers) == {
        "orchestrator",
        "research",
        "analyst",
        "executor",
        "mcp-server",
        "guardrails",
        "participant-ui",
    }
    assert all(item["image"].endswith(f"@{TEST_DIGEST}") for item in containers.values())
    assert pod_spec["serviceAccountName"] == "multi-agent"

    orchestrator = containers["orchestrator"]
    assert orchestrator["readinessProbe"]["httpGet"] == {
        "path": "/ready",
        "port": "orchestrator",
    }
    for name in ("research", "analyst", "executor"):
        assert containers[name]["readinessProbe"]["httpGet"]["path"] == "/health"
    assert containers["executor"]["envFrom"] == [
        {"configMapRef": {"name": "workflow-policy", "optional": True}}
    ]
    assert "envFrom" not in containers["research"]
    assert "envFrom" not in containers["analyst"]
    assert containers["participant-ui"]["readinessProbe"]["httpGet"] == {
        "path": "/",
        "port": "ui",
    }


def test_multi_agent_model_and_service_auth_come_only_from_the_runtime_secret():
    _, documents = _render()
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    containers = {
        item["name"]: item
        for item in deployment["spec"]["template"]["spec"]["containers"]
    }

    for name in ("orchestrator", "research", "analyst", "executor"):
        env = _env(containers[name])
        for key in ("MODEL_ENDPOINT", "MODEL_API_KEY", "MODEL_NAME"):
            assert env[key]["valueFrom"]["secretKeyRef"] == {
                "name": "multi-agent-runtime",
                "key": key,
            }
    orchestrator_env = _env(containers["orchestrator"])
    for key in ("MODEL_SIMPLE", "MODEL_COMPLEX"):
        assert orchestrator_env[key]["valueFrom"]["secretKeyRef"] == {
            "name": "multi-agent-runtime",
            "key": "MODEL_NAME",
        }
    for name in ("orchestrator", "research", "analyst", "executor"):
        env = _env(containers[name])
        assert env["AGENT_AUTH_TOKEN"]["valueFrom"]["secretKeyRef"] == {
            "name": "multi-agent-runtime",
            "key": "AGENT_AUTH_TOKEN",
        }
    participant_ui_env = _env(containers["participant-ui"])
    assert participant_ui_env["AGENT_AUTH_TOKEN"]["valueFrom"]["secretKeyRef"] == {
        "name": "multi-agent-runtime",
        "key": "AGENT_AUTH_TOKEN",
    }
    assert participant_ui_env["UI_WORKFLOW_TIMEOUT"] == {
        "name": "UI_WORKFLOW_TIMEOUT",
        "value": "300",
    }


def test_multi_agent_probes_tolerate_a_long_participant_workflow():
    _, documents = _render()
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]

    # A comprehensive workflow can keep an application event loop occupied for
    # 70-100 seconds.  One busy sidecar must not remove the complete seven-
    # container seat from its Service or trigger a liveness restart.
    for container in containers:
        readiness = container["readinessProbe"]
        liveness = container["livenessProbe"]
        assert readiness["timeoutSeconds"] == 5, container["name"]
        assert readiness["failureThreshold"] >= 24, container["name"]
        assert liveness["timeoutSeconds"] == 5, container["name"]
        assert liveness["failureThreshold"] >= 6, container["name"]

    orchestrator = next(item for item in containers if item["name"] == "orchestrator")
    assert orchestrator["startupProbe"]["timeoutSeconds"] == 5


def test_multi_agent_services_routes_and_network_boundary_are_complete():
    _, documents = _render()
    resources = {(item["kind"], item["metadata"]["name"]): item for item in documents}

    for service in (
        "multi-agent",
        "multi-agent-research",
        "multi-agent-analyst",
        "multi-agent-executor",
        "multi-agent-mcp",
        "multi-agent-guardrails",
        "multi-agent-ui",
    ):
        assert ("Service", service) in resources
    assert ("Route", "multi-agent") in resources
    assert ("Route", "multi-agent-ui") in resources
    assert ("NetworkPolicy", "multi-agent-ingress") in resources

    for route_name in ("multi-agent", "multi-agent-ui"):
        route = resources[("Route", route_name)]
        assert route["metadata"]["annotations"][
            "haproxy.router.openshift.io/timeout"
        ] == "600s"
        assert route["spec"]["tls"]["termination"] == "edge"
        assert route["spec"]["tls"]["insecureEdgeTerminationPolicy"] == "Redirect"


def test_multi_agent_arena_build_is_pinned_and_adds_model_bearer_support():
    documents = [item for item in yaml.safe_load_all(BUILD_CONFIG.read_text()) if item]
    image_stream = next(
        item
        for item in documents
        if item["kind"] == "ImageStream"
        and item["metadata"]["name"] == "multi-agent-quickstart"
    )
    assert image_stream

    build = next(
        item
        for item in documents
        if item["kind"] == "BuildConfig"
        and item["metadata"]["name"] == "multi-agent-quickstart"
    )
    assert build["spec"]["source"]["git"] == {
        "uri": SOURCE_REPOSITORY,
        "ref": SOURCE_REVISION,
    }
    assert build["spec"]["source"]["contextDir"] == "src"
    dockerfile = build["spec"]["source"]["dockerfile"]
    assert "python-311@sha256:" in dockerfile
    assert "MODEL_API_KEY" in dockerfile
    assert "Authorization" in dockerfile
    assert "AGENT_AUTH_TOKEN" in dockerfile
    assert "UI_WORKFLOW_TIMEOUT" in dockerfile
    assert "AGENT_MAX_TOKENS_OVERRIDE" in dockerfile
    assert 'headers={"Authorization": f"Bearer {AGENT_AUTH_TOKEN}"}' in dockerfile
    assert "ui.py" in dockerfile
    assert 'huggingface-hub==0.25.2' in dockerfile
    assert '"/ready"' in dockerfile
    assert "auth.py" in dockerfile
    assert "requirements.txt" not in dockerfile
    assert ":latest" not in dockerfile
    assert build["spec"]["output"]["to"]["name"] == (
        "multi-agent-quickstart:source-8a8e024"
    )
