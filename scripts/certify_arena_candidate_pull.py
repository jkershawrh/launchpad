"""Probe one immutable GHCR candidate in a disposable Arena namespace.

Dry-run by default. Execution never changes the active kubectl context, touches
an existing lab namespace, or emits cluster/provider output into the receipt.
This is one-seat image pull evidence, not release or full-node certification.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import time
from collections.abc import Callable
from typing import Any

ARENA_SERVER = "https://api.arena.fm2aihpcsed.com:6443"
IMAGE = re.compile(r"^ghcr\.io/jkershawrh/hybrid-fraud-detection@sha256:[0-9a-f]{64}$")
SUFFIX = re.compile(r"^[0-9a-f]{8}$")
SCHEMA = "launchpad.redhat.com/catalog-intake-arena-pull-probe/v1"
Runner = Callable[..., subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]


def _run(
    runner: Runner,
    context: str,
    args: list[str],
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return runner(
        ["oc", f"--context={context}", *args],
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _namespace_manifest(name: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": name,
            "labels": {
                "app.kubernetes.io/managed-by": "launchpad-intake-cert",
                "launchpad.redhat.com/purpose": "candidate-image-pull",
            },
        },
    }


def _pod_manifest(name: str, image: str) -> dict[str, Any]:
    smoke = (
        "from fastapi.testclient import TestClient; from scorer import app; "
        "c=TestClient(app); assert c.get('/ready').status_code==200; "
        "assert c.post('/api/v1/score',json={'amount':50,'country':'US',"
        "'category':'retail'}).status_code==200"
    )
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "candidate-smoke", "namespace": name},
        "spec": {
            "automountServiceAccountToken": False,
            "restartPolicy": "Never",
            "terminationGracePeriodSeconds": 0,
            "containers": [
                {
                    "name": "candidate",
                    "image": image,
                    "imagePullPolicy": "Always",
                    "command": ["python", "-c", smoke],
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "capabilities": {"drop": ["ALL"]},
                        "runAsNonRoot": True,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "500m", "memory": "512Mi"},
                    },
                }
            ],
        },
    }


def probe(
    image: str,
    context: str,
    *,
    execute: bool = False,
    runner: Runner = subprocess.run,
    namespace_suffix: str | None = None,
    sleeper: Sleeper = time.sleep,
) -> dict[str, Any]:
    """Run a bounded, disposable probe; return only coded findings."""

    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "cluster": "arena",
        "image": image if IMAGE.fullmatch(image) else None,
        "status": "blocked",
        "findings": [],
        "namespace": None,
        "cleanup": "not-needed",
        "release_eligible": False,
    }
    if not IMAGE.fullmatch(image) or not context or context.startswith("-"):
        report["findings"] = ["probe-input-invalid"]
        return report
    if namespace_suffix is not None and not SUFFIX.fullmatch(namespace_suffix):
        report["findings"] = ["probe-input-invalid"]
        return report
    if not execute:
        report["status"] = "planned"
        return report

    try:
        server = _run(runner, context, ["whoami", "--show-server"], timeout=10)
        if server.returncode != 0 or server.stdout.strip() != ARENA_SERVER:
            report["findings"] = ["arena-server-mismatch"]
            return report
        identity = _run(runner, context, ["whoami"], timeout=10)
        if identity.returncode != 0 or not identity.stdout.strip():
            report["findings"] = ["arena-auth-unavailable"]
            return report
    except (OSError, subprocess.TimeoutExpired):
        report["findings"] = ["arena-preflight-unavailable"]
        return report

    name = "launchpad-image-cert-" + (namespace_suffix or secrets.token_hex(4))
    report["namespace"] = name
    created = False
    uid: str | None = None
    try:
        namespace = _run(
            runner,
            context,
            ["create", "-f", "-", "-o", "json"],
            payload=_namespace_manifest(name),
        )
        if namespace.returncode != 0:
            report["findings"] = ["namespace-create-failed"]
            return report
        created = True
        uid = str(json.loads(namespace.stdout)["metadata"]["uid"])
        if not uid:
            report["findings"] = ["namespace-identity-missing"]
            return report

        pod = _run(
            runner,
            context,
            ["create", "-f", "-", "-o", "json"],
            payload=_pod_manifest(name, image),
        )
        if pod.returncode != 0:
            report["findings"] = ["pod-create-failed"]
            return report

        for _ in range(60):
            observed = _run(
                runner,
                context,
                ["get", "pod", "candidate-smoke", "-n", name, "-o", "json"],
                timeout=10,
            )
            if observed.returncode != 0:
                report["findings"] = ["pod-observation-failed"]
                break
            status = json.loads(observed.stdout).get("status") or {}
            phase = status.get("phase")
            if phase == "Succeeded":
                containers = status.get("containerStatuses") or []
                image_id = containers[0].get("imageID", "") if containers else ""
                if image_id.endswith(image):
                    report["status"] = "passed"
                else:
                    report["findings"] = ["pulled-digest-mismatch"]
                break
            if phase == "Failed":
                report["findings"] = ["pod-failed"]
                break
            sleeper(3)
        else:
            report["findings"] = ["pod-timeout"]
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        report["findings"] = ["probe-execution-unavailable"]
    finally:
        if created:
            report["cleanup"] = "failed"
            try:
                actual = _run(runner, context, ["get", "namespace", name, "-o", "json"])
                actual_uid = (
                    str(json.loads(actual.stdout)["metadata"]["uid"])
                    if actual.returncode == 0
                    else None
                )
                if uid and actual_uid == uid:
                    deleted = _run(
                        runner,
                        context,
                        ["delete", "namespace", name, "--wait=true", "--timeout=90s"],
                        timeout=110,
                    )
                    if deleted.returncode == 0:
                        report["cleanup"] = "passed"
            except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
                pass
            if report["cleanup"] != "passed":
                report["status"] = "blocked"
                report["findings"].append("namespace-cleanup-unverified")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    report = probe(args.image, args.context, execute=args.execute)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"planned", "passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
