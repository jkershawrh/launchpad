#!/usr/bin/env python3
"""Read-only, fail-closed preflight for an external event canary.

This command never creates, changes, or deletes cluster resources. It verifies
the permanent public origin and the exact OpenShift target before an operator
is allowed to start the separately approved live acceptance workflow.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

REQUIRED_DEPLOYMENTS = (
    "backend",
    "lifecycle-worker",
    "public-access-gateway",
    "cloudflare-tunnel",
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _http_check(
    url: str,
    *,
    expected_status: int = 200,
    timeout_seconds: float = 15,
) -> tuple[dict[str, Any], requests.Response | None]:
    started = datetime.now(UTC)
    try:
        response = requests.get(url, timeout=timeout_seconds, verify=True)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return (
            {
                "passed": response.status_code == expected_status,
                "http_status": response.status_code,
                "tls_verified": True,
                "duration_seconds": round(elapsed, 3),
            },
            response,
        )
    except requests.RequestException as exc:
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return (
            {
                "passed": False,
                "http_status": None,
                "tls_verified": False,
                "duration_seconds": round(elapsed, 3),
                "error_type": type(exc).__name__,
            },
            None,
        )


def _oc(
    kubeconfig: Path,
    *args: str,
    timeout_seconds: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["oc", "--kubeconfig", str(kubeconfig), *args],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def evaluate_preflight(
    *,
    public_origin: str,
    kubeconfig: Path,
    expected_api_server: str,
    namespace: str,
) -> dict[str, Any]:
    origin = public_origin.rstrip("/")
    checks: dict[str, Any] = {}

    health, health_response = _http_check(urljoin(f"{origin}/", "health"))
    if health_response is not None:
        try:
            payload = health_response.json()
        except ValueError:
            payload = {}
        health["marker_present"] = payload.get("status") == "ok"
        health["passed"] = health["passed"] and health["marker_present"]
    else:
        health["marker_present"] = False
    checks["public_health"] = health

    discovery_url = urljoin(
        f"{origin}/",
        "realms/launchpad-public/.well-known/openid-configuration",
    )
    oidc, oidc_response = _http_check(discovery_url)
    issuer = ""
    authorization_endpoint = ""
    token_endpoint = ""
    if oidc_response is not None:
        try:
            discovery = oidc_response.json()
        except ValueError:
            discovery = {}
        issuer = str(discovery.get("issuer", ""))
        authorization_endpoint = str(discovery.get("authorization_endpoint", ""))
        token_endpoint = str(discovery.get("token_endpoint", ""))
    expected_issuer = f"{origin}/realms/launchpad-public"
    oidc.update(
        {
            "issuer_matches": issuer == expected_issuer,
            "authorization_endpoint_same_origin": authorization_endpoint.startswith(
                f"{origin}/"
            ),
            "token_endpoint_same_origin": token_endpoint.startswith(f"{origin}/"),
        }
    )
    oidc["passed"] = oidc["passed"] and all(
        oidc[key]
        for key in (
            "issuer_matches",
            "authorization_endpoint_same_origin",
            "token_endpoint_same_origin",
        )
    )
    checks["oidc_discovery"] = oidc

    configured = _oc(
        kubeconfig,
        "config",
        "view",
        "--minify",
        "-o",
        "jsonpath={.clusters[0].cluster.server}",
    )
    configured_server = configured.stdout.strip()
    checks["target_cluster"] = {
        "passed": configured.returncode == 0
        and configured_server == expected_api_server,
        "expected_api_server": expected_api_server,
        "configured_api_server": configured_server,
    }

    authenticated = _oc(kubeconfig, "whoami")
    checks["cluster_authentication"] = {
        "passed": authenticated.returncode == 0,
        "error_type": None if authenticated.returncode == 0 else "unauthorized",
    }

    permission = _oc(
        kubeconfig,
        "auth",
        "can-i",
        "get",
        "deployments.apps",
        "-n",
        namespace,
    )
    checks["read_permission"] = {
        "passed": permission.returncode == 0 and permission.stdout.strip() == "yes",
        "namespace": namespace,
    }

    deployments = _oc(
        kubeconfig,
        "-n",
        namespace,
        "get",
        "deployments.apps",
        "-o",
        "json",
    )
    deployment_summary: dict[str, dict[str, int | bool]] = {}
    if deployments.returncode == 0:
        try:
            items = json.loads(deployments.stdout).get("items", [])
        except (ValueError, AttributeError):
            items = []
        by_name = {item.get("metadata", {}).get("name"): item for item in items}
        for name in REQUIRED_DEPLOYMENTS:
            item = by_name.get(name, {})
            desired = int(item.get("spec", {}).get("replicas") or 0)
            available = int(item.get("status", {}).get("availableReplicas") or 0)
            deployment_summary[name] = {
                "desired": desired,
                "available": available,
                "ready": desired > 0 and available == desired,
            }
    else:
        deployment_summary = {
            name: {"desired": 0, "available": 0, "ready": False}
            for name in REQUIRED_DEPLOYMENTS
        }
    checks["required_deployments"] = {
        "passed": deployments.returncode == 0
        and all(item["ready"] for item in deployment_summary.values()),
        "namespace": namespace,
        "deployments": deployment_summary,
    }

    ready = all(check.get("passed") is True for check in checks.values())
    return {
        "schema_version": "launchpad.intel.com/live-acceptance-preflight/v1",
        "observed_at": _now(),
        "public_origin": origin,
        "expected_api_server": expected_api_server,
        "namespace": namespace,
        "mode": "read-only",
        "ready_for_canary": ready,
        "checks": checks,
        "contains_plaintext_credentials": False,
        "cluster_resources_mutated": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--kubeconfig", required=True, type=Path)
    parser.add_argument("--expected-api-server", required=True)
    parser.add_argument("--namespace", default="partner-ai-launchpad")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.kubeconfig.is_file():
        parser.error(f"kubeconfig does not exist: {args.kubeconfig}")
    if not args.public_origin.startswith("https://"):
        parser.error("public origin must use HTTPS")

    result = evaluate_preflight(
        public_origin=args.public_origin,
        kubeconfig=args.kubeconfig,
        expected_api_server=args.expected_api_server,
        namespace=args.namespace,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["ready_for_canary"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
