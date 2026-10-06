#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg2


def _count(command: list[str]) -> int:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _seat_namespace_count() -> int:
    result = subprocess.run(
        ["oc", "get", "namespace", "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    items = json.loads(result.stdout)["items"]
    return sum(
        1
        for item in items
        if item["metadata"]["name"].startswith("launchpad-flightpath-candida-")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--expected-catalogs", required=True, type=int)
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--run-started-at", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir)
    bundles = []
    for path in sorted(evidence_dir.glob("*.json")):
        if path.name.endswith("zero-residue.json"):
            continue
        data = json.loads(path.read_text())
        if not str(data.get("run_id", "")).startswith(args.run_prefix):
            continue
        if data.get("contract", {}).get("git_commit") != args.candidate_commit:
            continue
        bundles.append(
            {
                "catalog_item_id": data.get("catalog_item_id"),
                "result": data.get("result"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    with psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.set_session(readonly=True, autocommit=False)
        with connection.cursor() as cursor:
            global_queries = {
                "active_sessions": "SELECT count(*) FROM lab_sessions WHERE status <> 'reclaimed'",
                "active_workshops": (
                    "SELECT count(*) FROM workshops "
                    "WHERE status NOT IN ('completed', 'completed_with_errors', 'failed', 'reclaimed')"
                ),
            }
            database_counts = {}
            for name, query in global_queries.items():
                cursor.execute(query)
                database_counts[name] = int(cursor.fetchone()[0])
            scoped_queries = {
                "residual_entitlements_created_by_run": "SELECT count(*) FROM participant_entitlements WHERE created_at >= %s",
                "residual_access_policies_created_by_run": "SELECT count(*) FROM access_policies WHERE created_at >= %s",
                "residual_access_sessions_created_by_run": "SELECT count(*) FROM access_sessions WHERE created_at >= %s",
                "residual_identities_created_by_run": "SELECT count(*) FROM participant_identities WHERE created_at >= %s",
                "residual_session_credentials_created_by_run": "SELECT count(*) FROM lab_sessions WHERE created_at >= %s AND (coalesce(data->>'maas_api_key', '') <> '' OR coalesce(data#>>'{resources,maas_api_key}', '') <> '')",
            }
            for name, query in scoped_queries.items():
                cursor.execute(query, (args.run_started_at,))
                database_counts[name] = int(cursor.fetchone()[0])

    resource_counts = {
        "seat_namespaces": _seat_namespace_count(),
        "session_routes": _count(
            ["oc", "get", "routes.route.openshift.io", "-A", "-l", "launchpad.redhat.com/session-id", "-o", "name"]
        ),
        "session_rolebindings": _count(
            ["oc", "get", "rolebindings.rbac.authorization.k8s.io", "-A", "-l", "launchpad.redhat.com/session-id", "-o", "name"]
        ),
        "session_secrets": _count(
            ["oc", "get", "secrets", "-A", "-l", "launchpad.redhat.com/session-id", "-o", "name"]
        ),
        "argo_applications": _count(
            ["oc", "get", "applications.argoproj.io", "-A", "-l", "launchpad.redhat.com/session-id", "-o", "name"]
        ),
    }
    all_green = len(bundles) == args.expected_catalogs and all(
        x["result"] == "GREEN-live" for x in bundles
    )
    zero_residue = all(value == 0 for value in database_counts.values()) and all(
        value == 0 for value in resource_counts.values()
    )
    report = {
        "schema": "launchpad.redhat.com/staging-zero-residue/v1",
        "candidate_git_commit": args.candidate_commit,
        "candidate_manifest_sha256": args.manifest_sha256,
        "expected_catalogs": args.expected_catalogs,
        "observed_at": datetime.now(UTC).isoformat(),
        "certification_bundles": bundles,
        "database_counts": database_counts,
        "resource_counts": resource_counts,
        "all_catalogs_green": all_green,
        "zero_residue": zero_residue,
        "result": "GREEN-live" if all_green and zero_residue else "RED-live",
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["result"] == "GREEN-live" else 1


if __name__ == "__main__":
    raise SystemExit(main())
