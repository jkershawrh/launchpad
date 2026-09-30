#!/usr/bin/env python3
"""Optional Show -> Learn -> Do -> Prove path for the open AI sandbox."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


LABEL_KEY = "launchpad.redhat.com/guided-start"
WORKLOAD_NAME = "guided-start"
DEFAULT_WORKSPACE = Path("/home/lab-user/workspace")
GUIDE_PATH = Path("/opt/launchpad/guided-start.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _api_base(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def build_manifests(*, namespace: str, image: str) -> list[dict[str, Any]]:
    """Return the one-pod guided workload and its namespace-scoped support objects."""
    labels = {"app": WORKLOAD_NAME, LABEL_KEY: "true"}
    return [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": WORKLOAD_NAME,
                "namespace": namespace,
                "labels": labels,
            },
            "data": {
                "index.html": (
                    "<!doctype html><title>Launchpad guided start</title>"
                    "<h1>OpenShift workload is ready</h1>"
                    "<p>This response came from your namespace-scoped pod.</p>"
                )
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": WORKLOAD_NAME,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": WORKLOAD_NAME}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                        "containers": [
                            {
                                "name": "web",
                                "image": image,
                                "imagePullPolicy": "IfNotPresent",
                                "command": [
                                    "python3",
                                    "-m",
                                    "http.server",
                                    "8080",
                                    "--directory",
                                    "/opt/guided",
                                ],
                                "ports": [{"name": "http", "containerPort": 8080}],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]},
                                    "runAsNonRoot": True,
                                },
                                "resources": {
                                    "requests": {"cpu": "25m", "memory": "32Mi"},
                                    "limits": {"cpu": "100m", "memory": "96Mi"},
                                },
                                "readinessProbe": {
                                    "httpGet": {"path": "/", "port": "http"},
                                    "initialDelaySeconds": 1,
                                    "periodSeconds": 2,
                                },
                                "volumeMounts": [
                                    {
                                        "name": "content",
                                        "mountPath": "/opt/guided",
                                        "readOnly": True,
                                    }
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "content",
                                "configMap": {"name": WORKLOAD_NAME},
                            }
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": WORKLOAD_NAME,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": {
                "selector": {"app": WORKLOAD_NAME},
                "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
            },
        },
    ]


def complete_model_probe(
    *, endpoint: str, api_key: str, client: Any | None = None
) -> dict[str, Any]:
    """Make one real completion or return a truthful unavailable result."""
    if not endpoint or not api_key:
        return {
            "status": "unavailable",
            "model": None,
            "reason": "Launchpad model endpoint or seat credential is not configured",
        }

    http = client or httpx.Client(timeout=90.0)
    base = _api_base(endpoint)
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        models_response = http.get(f"{base}/models", headers=headers)
        models_response.raise_for_status()
        models = models_response.json().get("data") or []
        model = next(
            (item.get("id") for item in models if isinstance(item, dict) and item.get("id")),
            None,
        )
        if not model:
            return {
                "status": "unavailable",
                "model": None,
                "reason": "The model endpoint returned no available model IDs",
            }
        completion = http.post(
            f"{base}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "In one sentence, explain why a namespace boundary matters "
                            "for an OpenShift development sandbox."
                        ),
                    }
                ],
                "temperature": 0,
                "max_tokens": 80,
            },
        )
        completion.raise_for_status()
        payload = completion.json()
        return {
            "status": "live",
            "model": payload.get("model") or model,
            "response": payload["choices"][0]["message"]["content"],
            "usage": payload.get("usage") or {},
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "model": None,
            "reason": f"Live model request failed: {type(exc).__name__}",
        }
    finally:
        if client is None:
            http.close()


def _contains_sensitive_key(value: Any) -> bool:
    forbidden = {
        "api_key",
        "apikey",
        "password",
        "secret",
        "token",
        "access_token",
        "credential",
    }
    if isinstance(value, dict):
        return any(
            str(key).lower().replace("-", "_") in forbidden
            or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def write_proof(path: Path, proof: dict[str, Any]) -> None:
    """Write a participant-readable proof artifact without credentials."""
    if _contains_sensitive_key(proof):
        raise ValueError("Proof contains a credential-like key")
    document = {
        "schema_version": "launchpad-sandbox-guided-start/v1",
        "recorded_at": _utc_now(),
        **proof,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def _oc(*args: str, input_value: str | None = None, check: bool = True) -> str:
    completed = subprocess.run(
        ["oc", *args],
        input=input_value,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"oc {' '.join(args)} failed: {message}")
    return completed.stdout.strip()


def _namespace() -> str:
    namespace = os.environ.get("SANDBOX_NAMESPACE", "").strip() or _oc("project", "-q")
    if not namespace:
        raise RuntimeError("Unable to determine the sandbox namespace")
    return namespace


def learn() -> dict[str, Any]:
    namespace = _namespace()
    current = _oc("project", "-q")
    own_edit = _oc("auth", "can-i", "create", "deployments.apps", "-n", namespace)
    cross_namespace = _oc(
        "auth", "can-i", "get", "pods", "-n", "partner-ai-launchpad"
    )
    nodes = _oc("auth", "can-i", "get", "nodes")
    result = {
        "namespace": namespace,
        "current_project_matches": current == namespace,
        "own_edit": own_edit == "yes",
        "cross_namespace": cross_namespace == "yes",
        "cluster_nodes": nodes == "yes",
    }
    if not result["current_project_matches"] or not result["own_edit"]:
        raise RuntimeError("The terminal is not correctly scoped to this sandbox namespace")
    if result["cross_namespace"] or result["cluster_nodes"]:
        raise RuntimeError("The sandbox identity has access outside its intended boundary")
    return result


def deploy_workload() -> dict[str, Any]:
    namespace = _namespace()
    image = _oc(
        "get",
        "deployment/sandbox",
        "-n",
        namespace,
        "-o",
        "jsonpath={.spec.template.spec.containers[0].image}",
    )
    manifests = {
        "apiVersion": "v1",
        "kind": "List",
        "items": build_manifests(namespace=namespace, image=image),
    }
    _oc("apply", "-f", "-", input_value=json.dumps(manifests))
    _oc(
        "rollout",
        "status",
        f"deployment/{WORKLOAD_NAME}",
        "-n",
        namespace,
        "--timeout=180s",
    )
    response = _oc(
        "exec",
        f"deployment/{WORKLOAD_NAME}",
        "-n",
        namespace,
        "--",
        "python3",
        "-c",
        "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/', timeout=5).status)",
    )
    return {
        "status": "ready" if response == "200" else "failed",
        "deployment": WORKLOAD_NAME,
        "replicas": 1,
        "http_status": int(response),
    }


def cleanup() -> dict[str, Any]:
    namespace = _namespace()
    _oc(
        "delete",
        "deployment,service,configmap",
        WORKLOAD_NAME,
        "-n",
        namespace,
        "--ignore-not-found=true",
    )
    remaining = _oc(
        "get",
        "deployment,service,configmap,pod",
        "-n",
        namespace,
        "-l",
        f"{LABEL_KEY}=true",
        "-o",
        "name",
        check=False,
    )
    return {
        "status": "complete" if not remaining else "incomplete",
        "remaining_resources": remaining.splitlines() if remaining else [],
    }


def _workspace() -> Path:
    workspace = Path(os.environ.get("WORKSPACE", str(DEFAULT_WORKSPACE)))
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def prove() -> dict[str, Any]:
    namespace = _namespace()
    isolation = learn()
    workload_name = _oc(
        "get",
        f"deployment/{WORKLOAD_NAME}",
        "-n",
        namespace,
        "-o",
        "name",
        check=False,
    )
    workload = {
        "status": "ready" if workload_name else "not_created",
        "deployment": WORKLOAD_NAME if workload_name else None,
    }
    model = complete_model_probe(
        endpoint=os.environ.get("LITELLM_API_BASE")
        or os.environ.get("MODEL_ENDPOINT", ""),
        api_key=os.environ.get("LITELLM_API_KEY")
        or os.environ.get("MAAS_SESSION_KEY", ""),
    )
    proof = {
        "namespace": namespace,
        "namespace_isolation": isolation,
        "workload": workload,
        "model": model,
        "cleanup": {"status": "pending"},
    }
    write_proof(_workspace() / "guided-start-proof.json", proof)
    return proof


def _print(value: Any) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    command = args[0] if args else "show"
    if command == "show":
        _print(GUIDE_PATH.read_text())
    elif command == "learn":
        _print(learn())
    elif command == "do":
        _print(deploy_workload())
    elif command == "prove":
        _print(prove())
    elif command == "cleanup":
        result = cleanup()
        proof_path = _workspace() / "guided-start-proof.json"
        existing = json.loads(proof_path.read_text()) if proof_path.exists() else {}
        existing.pop("recorded_at", None)
        existing.pop("schema_version", None)
        existing["cleanup"] = result
        write_proof(proof_path, existing)
        _print(result)
        if result["status"] != "complete":
            return 1
    elif command == "all":
        _print(learn())
        _print(deploy_workload())
        _print(prove())
        result = cleanup()
        proof_path = _workspace() / "guided-start-proof.json"
        existing = json.loads(proof_path.read_text())
        existing.pop("recorded_at", None)
        existing.pop("schema_version", None)
        existing["cleanup"] = result
        write_proof(proof_path, existing)
        _print(result)
        if result["status"] != "complete":
            return 1
    else:
        print("Usage: launchpad-guided-start [show|learn|do|prove|cleanup|all]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
