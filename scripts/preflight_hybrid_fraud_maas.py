"""Read-only Arena MaaS prerequisite check for the Hybrid Fraud one-seat pilot.

Never reads Secret values or mutates a cluster. A green preflight only permits
candidate-scoped configuration work; it is not a lab or release certification.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from typing import Any

ARENA_SERVER = "https://api.arena.fm2aihpcsed.com:6443"
SCHEMA = "launchpad.redhat.com/hybrid-fraud-maas-preflight/v1"
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(runner: Runner, kubeconfig: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return runner(
        ["oc", f"--kubeconfig={kubeconfig}", *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def review(kubeconfig: str, *, runner: Runner = subprocess.run) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "cluster": "arena",
        "catalog_item_id": "hybrid-fraud-detection",
        "status": "RED",
        "findings": [],
        "release_eligible": False,
        "mutation_performed": False,
    }
    if not kubeconfig or kubeconfig.startswith("-"):
        report["findings"] = ["kubeconfig-invalid"]
        return report

    findings: set[str] = set()
    try:
        server = _run(runner, kubeconfig, ["whoami", "--show-server"])
        if server.returncode != 0 or server.stdout.strip() != ARENA_SERVER:
            findings.add("arena-context-unavailable")
            report["findings"] = sorted(findings)
            return report

        subscriptions = _run(runner, kubeconfig, ["get", "subscription", "-A", "-o", "json"])
        installed = (json.loads(subscriptions.stdout).get("items") or []) if subscriptions.returncode == 0 else []
        if not any((item.get("spec") or {}).get("name") == "rhcl-operator" for item in installed):
            findings.add("maas-connectivity-link-subscription-missing")

        for kind in (
            "maasmodelrefs.maas.opendatahub.io",
            "maassubscriptions.maas.opendatahub.io",
            "maasauthpolicies.maas.opendatahub.io",
        ):
            result = _run(runner, kubeconfig, ["get", "crd", kind, "-o", "name"])
            if result.returncode != 0:
                findings.add("maas-resource-api-unavailable")

        kuadrant_crd = _run(runner, kubeconfig, ["get", "crd", "kuadrants.kuadrant.io", "-o", "name"])
        if kuadrant_crd.returncode != 0:
            findings.add("maas-kuadrant-operator-missing")
        kuadrant = None
        if kuadrant_crd.returncode == 0:
            kuadrant = _run(
                runner,
                kubeconfig,
                ["get", "kuadrant", "kuadrant", "-n", "kuadrant-system", "-o", "json"],
            )
        conditions = []
        if kuadrant and kuadrant.returncode == 0:
            conditions = (json.loads(kuadrant.stdout).get("status") or {}).get("conditions", [])
        if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
            findings.add("maas-kuadrant-instance-not-ready")

        cluster = _run(runner, kubeconfig, ["get", "datasciencecluster", "-o", "json"])
        items = (json.loads(cluster.stdout).get("items") or []) if cluster.returncode == 0 else []
        if not any(
            (((item.get("spec") or {}).get("components") or {}).get("aigateway") or {})
            .get("modelsAsAService", {}).get("managementState") == "Managed"
            for item in items
        ):
            findings.add("maas-component-disabled")

        tenant_config = _run(
            runner,
            kubeconfig,
            ["get", "maastenantconfig", "default-tenant", "-n", "models-as-a-service", "-o", "json"],
        )
        infra_namespace = (
            (json.loads(tenant_config.stdout).get("status") or {}).get("infraNamespace")
            if tenant_config.returncode == 0 else None
        )
        if not infra_namespace:
            findings.add("maas-infra-namespace-unresolved")
        elif not any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in (json.loads(tenant_config.stdout).get("status") or {}).get("conditions", [])
        ):
            findings.add("maas-tenant-config-not-ready")

        tenant = _run(
            runner,
            kubeconfig,
            ["get", "aitenant", "models-as-a-service", "-n", "ai-tenants", "-o", "json"],
        )
        if tenant.returncode != 0:
            findings.add("maas-tenant-unavailable")
        else:
            tenant_conditions = (json.loads(tenant.stdout).get("status") or {}).get("conditions", [])
            if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in tenant_conditions):
                findings.add("maas-tenant-not-ready")

        if infra_namespace:
            database = _run(
                runner,
                kubeconfig,
                ["get", "secret", "maas-db-config", "-n", infra_namespace, "-o", "name"],
            )
            if database.returncode != 0:
                findings.add("maas-database-secret-missing")

        authorino = _run(runner, kubeconfig, ["get", "authorino", "authorino", "-n", "kuadrant-system", "-o", "json"])
        if authorino.returncode != 0:
            findings.add("maas-authorino-not-ready")
        else:
            authorino_data = json.loads(authorino.stdout)
            tls_enabled = (((authorino_data.get("spec") or {}).get("listener") or {}).get("tls") or {}).get("enabled")
            ready = any(
                c.get("type") == "Ready" and c.get("status") == "True"
                for c in (authorino_data.get("status") or {}).get("conditions", [])
            )
            if not tls_enabled or not ready:
                findings.add("maas-authorino-not-ready")

        gateway = _run(
            runner,
            kubeconfig,
            ["get", "gateway", "maas-default-gateway", "-n", "openshift-ingress", "-o", "json"],
        )
        if gateway.returncode != 0:
            findings.add("maas-gateway-not-ready")
        else:
            gateway_data = json.loads(gateway.stdout)
            tls_bootstrap = ((gateway_data.get("metadata") or {}).get("annotations") or {}).get(
                "security.opendatahub.io/authorino-tls-bootstrap"
            )
            programmed = any(
                c.get("type") == "Programmed" and c.get("status") == "True"
                for c in (gateway_data.get("status") or {}).get("conditions", [])
            )
            if tls_bootstrap != "true" or not programmed:
                findings.add("maas-gateway-not-ready")

        if infra_namespace:
            api = _run(
                runner,
                kubeconfig,
                ["get", "deployment", "maas-api", "-n", infra_namespace, "-o", "json"],
            )
            if api.returncode != 0:
                findings.add("maas-api-unavailable")
            else:
                deployment = json.loads(api.stdout)
                if (deployment.get("status") or {}).get("readyReplicas", 0) < 1:
                    findings.add("maas-api-unavailable")
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        findings.add("maas-preflight-unavailable")

    report["findings"] = sorted(findings)
    report["status"] = "ready-for-candidate-configuration" if not findings else "RED"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", required=True)
    args = parser.parse_args()
    report = review(args.kubeconfig)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready-for-candidate-configuration" else 2


if __name__ == "__main__":
    raise SystemExit(main())
