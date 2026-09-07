#!/usr/bin/env python3
"""Read-only placement preflight for the September 17 fleet event.

This command never creates or reclaims a workshop. It submits the exact three
capacity-preview requests with explicit admin target overrides and fails closed
if Launchpad rejects a target or substitutes a different cluster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

warnings.filterwarnings(
    "ignore",
    message="urllib3 v2 only supports OpenSSL 1.1.1+",
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    REPO_ROOT
    / "evidence/september-17-multicluster-three-workshop-readiness-2026-09-07.json"
)


def _utc_now() -> str:
    # timezone.utc keeps the operator script compatible with the macOS Python 3.9.
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: UP017


def load_event_contract(path: Path | str = DEFAULT_CONTRACT) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise TypeError("event readiness contract must be a JSON object")
    return payload


def build_capacity_requests(contract: dict[str, Any]) -> list[dict[str, Any]]:
    if contract.get("schema") != "launchpad.redhat.com/event-readiness/v3":
        raise ValueError("event readiness contract must use schema v3")
    if contract.get("workshop_affinity") != "one-workshop-one-cluster":
        raise ValueError("event requires whole-workshop cluster affinity")
    if contract.get("seat_splitting_allowed") is not False:
        raise ValueError("event contract must prohibit seat splitting")
    if contract.get("public_access_certified") is not False:
        raise ValueError("this preflight is restricted to internal access")

    workshops = sorted(
        contract.get("workshops", []), key=lambda item: item.get("provision_order", 0)
    )
    targets = contract.get("candidate_cluster_targets", {})
    if len(workshops) != 3:
        raise ValueError("event contract must contain exactly three workshops")

    selected_targets: list[str] = []
    requests_to_preview: list[dict[str, Any]] = []
    for workshop in workshops:
        catalog_item_id = str(workshop.get("catalog_item_id", ""))
        target_cluster = str(targets.get(catalog_item_id, ""))
        if not catalog_item_id or not target_cluster:
            raise ValueError("every workshop must have an explicit target cluster")
        if workshop.get("candidate_cluster_id") != target_cluster:
            raise ValueError(
                f"candidate target mismatch for {catalog_item_id}: {target_cluster}"
            )
        if workshop.get("seat_count") != 25:
            raise ValueError("every September event workshop must contain 25 seats")
        activation = contract.get("target_activation", {}).get(target_cluster, {})
        if activation.get("event_override_required") is not True:
            raise ValueError(f"event target override is not required for {target_cluster}")

        selected_targets.append(target_cluster)
        requests_to_preview.append(
            {
                "tenant_id": "smoke-test-tenant",
                "catalog_item_id": catalog_item_id,
                "num_users": 25,
                "name": f"September 17 preflight: {catalog_item_id}",
                "owner_id": "september-17-event-owner",
                "ttl": "4h",
                "purpose": "event-preflight",
                "target_cluster": target_cluster,
                "certification_override": False,
                "exposure_policy": "internal",
            }
        )

    if len(set(selected_targets)) != len(selected_targets):
        raise ValueError("event topology requires one distinct cluster per workshop")
    if sum(item["num_users"] for item in requests_to_preview) != 75:
        raise ValueError("event contract must reserve exactly 75 participant seats")
    return requests_to_preview


def run_capacity_preflight(
    contract: dict[str, Any],
    *,
    api_base_url: str,
    api_key: str,
    session: Any | None = None,
    verify: bool | str = True,
) -> dict[str, Any]:
    import requests

    if not api_key:
        raise ValueError("an administrator API credential is required")
    base = api_base_url.rstrip("/")
    if not base.endswith("/api/v1"):
        base = f"{base}/api/v1"
    http = session or requests.Session()
    expected_targets = set(contract["candidate_cluster_targets"].values())
    target_inspection: dict[str, Any] = {
        "passed": False,
        "mutates_cluster": False,
        "targets": {},
    }
    try:
        response = http.get(
            f"{base}/admin/clusters/preflight",
            headers={"X-API-Key": api_key},
            timeout=60,
            verify=verify,
        )
        payload = response.json()
        observed = {
            item.get("cluster_id"): item
            for item in payload.get("clusters", [])
            if item.get("cluster_id") in expected_targets
        }
        target_inspection.update(
            {
                "http_status": response.status_code,
                "targets": observed,
            }
        )
        target_inspection["passed"] = bool(
            response.status_code == 200
            and payload.get("mutates_cluster") is False
            and set(observed) == expected_targets
            and all(item.get("healthy") is True for item in observed.values())
        )
    except (requests.RequestException, ValueError, TypeError) as exc:
        target_inspection["error"] = type(exc).__name__

    checks: list[dict[str, Any]] = []

    for body in build_capacity_requests(contract):
        expected = body["target_cluster"]
        check: dict[str, Any] = {
            "catalog_item_id": body["catalog_item_id"],
            "expected_cluster": expected,
            "seats": body["num_users"],
            "passed": False,
        }
        try:
            response = http.post(
                f"{base}/workshops/capacity-preview",
                headers={"X-API-Key": api_key},
                json=body,
                timeout=60,
                verify=verify,
            )
            payload = response.json()
            selected = payload.get("selected_cluster")
            check.update(
                {
                    "http_status": response.status_code,
                    "can_provision": payload.get("can_provision", False),
                    "selected_cluster": selected,
                    "placement_reason": payload.get("placement_reason")
                    or payload.get("reason", ""),
                }
            )
            check["passed"] = bool(
                response.status_code == 200
                and payload.get("can_provision") is True
                and selected == expected
            )
        except (requests.RequestException, ValueError, TypeError) as exc:
            check["error"] = type(exc).__name__
        checks.append(check)

    return {
        "schema": "launchpad.redhat.com/event-preflight-evidence/v1",
        "evidence_id": (
            "SEPTEMBER-17-MULTICLUSTER-PREFLIGHT-"
            f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"  # noqa: UP017
        ),
        "observed_at": _utc_now(),
        "event_date": contract["event_date"],
        "mutates_cluster": False,
        "result": (
            "GREEN-live-preflight"
            if target_inspection["passed"]
            and len(checks) == 3
            and all(check["passed"] for check in checks)
            else "RED"
        ),
        "target_inspection": target_inspection,
        "checks": checks,
        "contains_plaintext_credentials": False,
    }


def _write_result(path: Path | None, result: dict[str, Any]) -> None:
    rendered = json.dumps(result, indent=2) + "\n"
    if path is None:
        print(rendered, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{checksum}  {path.name}\n"
    )
    print(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--api-base-url")
    parser.add_argument("--api-key-env", default="LAUNCHPAD_ADMIN_API_KEY")
    parser.add_argument("--ca-bundle")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    contract_path = Path(args.contract).resolve()
    contract = load_event_contract(contract_path)
    requests_to_preview = build_capacity_requests(contract)
    if args.contract_only:
        result = {
            "schema": "launchpad.redhat.com/event-preflight-evidence/v1",
            "evidence_id": "SEPTEMBER-17-MULTICLUSTER-PREFLIGHT-CONTRACT",
            "observed_at": _utc_now(),
            "event_date": contract["event_date"],
            "mutates_cluster": False,
            "result": "GREEN-contract",
            "contract": str(contract_path),
            "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            "requests": requests_to_preview,
            "contains_plaintext_credentials": False,
        }
    else:
        import requests

        if not args.api_base_url:
            parser.error("--api-base-url is required unless --contract-only is used")
        verify: bool | str = True
        if args.insecure:
            verify = False
            requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
        elif args.ca_bundle:
            verify = str(Path(args.ca_bundle).resolve())
        result = run_capacity_preflight(
            contract,
            api_base_url=args.api_base_url,
            api_key=os.environ.get(args.api_key_env, ""),
            verify=verify,
        )

    _write_result(Path(args.output).resolve() if args.output else None, result)
    return 0 if result["result"].startswith("GREEN") else 1


if __name__ == "__main__":
    sys.exit(main())
