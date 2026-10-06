"""Read-only preflight for the single-origin browser certification gate.

The check validates catalog-to-profile coverage from Git and, unless disabled,
probes the permanent public origin with the system trust store. It never calls
the OpenShift API and never creates, changes, or reclaims a lab.
"""

from __future__ import annotations

import argparse
import json
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "certification/browser-access-profiles-v1.yaml"
EDGE_PATHS = (
    "/health",
    "/realms/launchpad-public/.well-known/openid-configuration",
)


def active_catalogs(root: Path = ROOT) -> set[str]:
    active = set()
    for path in (root / "catalog").glob("*/catalog-item.yaml"):
        item = yaml.safe_load(path.read_text(encoding="utf-8"))
        if item.get("status") == "active":
            active.add(item["catalog_item_id"])
    return active


def evaluate_source(root: Path = ROOT) -> dict:
    contract = yaml.safe_load(
        (root / "certification/browser-access-profiles-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    profiles = contract["spec"]["profiles"]
    active = active_catalogs(root)
    assignments = [
        catalog
        for profile in profiles.values()
        for catalog in profile.get("catalogs", [])
    ]
    assigned = set(assignments)
    representatives_valid = all(
        profile.get("representative") in profile.get("catalogs", [])
        and profile.get("representative") in active
        for profile in profiles.values()
    )
    checks = {
        "permanent_public_origin": (
            contract["metadata"].get("public_origin") == "https://labs.smg-helix.ai"
        ),
        "target_is_flightpath": contract["metadata"].get("target_cluster") == "flightpath",
        "every_active_catalog_assigned": assigned == active,
        "no_duplicate_assignments": len(assignments) == len(assigned),
        "representatives_are_active_members": representatives_valid,
        "shared_security_and_cleanup_gates": {
            "trusted_tls_without_browser_bypass",
            "openshift_console_sso",
            "cross_namespace_denied",
            "no_recursive_iframe",
            "reclaim_is_idempotent",
            "zero_residue",
        }
        <= set(contract["spec"].get("shared_gates", [])),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "active_catalog_count": len(active),
        "profile_count": len(profiles),
        "unassigned_catalogs": sorted(active - assigned),
        "unknown_catalogs": sorted(assigned - active),
    }


def probe_public_edge(
    origin: str,
    opener=urlopen,
    paths: tuple[str, ...] = EDGE_PATHS,
) -> dict:
    results = []
    context = ssl.create_default_context()
    for path in paths:
        check = {"path": path, "passed": False}
        try:
            request = Request(
                f"{origin}{path}",
                method="GET",
                headers={
                    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                    "User-Agent": "launchpad-browser-certification-preflight/1",
                },
            )
            with opener(request, timeout=10, context=context) as response:
                check["http_status"] = response.status
                check["passed"] = 200 <= response.status < 300
        except HTTPError as exc:
            check["http_status"] = exc.code
            check["error_type"] = type(exc).__name__
        except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            check["error_type"] = type(exc).__name__
        results.append(check)
    return {
        "origin": origin,
        "uses_system_trust_store": True,
        "passed": bool(results) and all(item["passed"] for item in results),
        "endpoints": results,
    }


def evaluate(root: Path = ROOT, *, network: bool = True, opener=urlopen) -> dict:
    contract = yaml.safe_load(
        (root / "certification/browser-access-profiles-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    source = evaluate_source(root)
    edge = (
        probe_public_edge(contract["metadata"]["public_origin"], opener=opener)
        if network
        else {"passed": None, "status": "not_run"}
    )
    return {
        "schema": "launchpad.redhat.com/browser-access-preflight/v1",
        "mutates_cluster": False,
        "source": source,
        "public_edge": edge,
        "passed": source["passed"] and (edge["passed"] is not False),
        "live_seat_proof": "not_run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="validate source contracts only; do not probe the public edge",
    )
    args = parser.parse_args()
    report = evaluate(network=not args.no_network)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
