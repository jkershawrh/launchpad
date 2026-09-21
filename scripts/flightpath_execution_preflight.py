"""Read-only source preflight for Flightpath execution-seat certification.

No cluster API calls, image pulls, DNS probes, orders, or mutations occur here.
The report deliberately leaves runtime proof open.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from app.domain.models import CatalogItem, LabRequest

PILOT_CATALOG_IDS = (
    "intel-llm-cpu-serving",
    "intel-xeon6-agent-201",
    "multi-agent-quickstart",
)


def evaluate(root: Path = ROOT) -> dict:
    overlay = yaml.safe_load(
        (root / "deploy/launchpad/overlays/arena/arena-clusters.yaml").read_text()
    )
    targets = {
        item["cluster_id"]: item
        for item in yaml.safe_load(overlay["data"]["clusters.yaml"])["clusters"]
    }
    target = targets["flightpath"]
    checks = {
        "target_enabled": target.get("enabled") is True,
        "dedicated_credential_ref": (
            target.get("credential_secret")
            == "partner-ai-launchpad/launchpad-flightpath-kubeconfig"
        ),
        "expected_api_and_ingress": (
            target.get("api_url") == "https://api.flightpath.fm2aihpcsed.com:6443"
            and target.get("ingress_domain") == "apps.flightpath.fm2aihpcsed.com"
        ),
        "showroom_images_explicit": all(
            target.get("image_references", {}).get(name)
            for name in ("showroom_terminal", "showroom_git_cloner")
        ),
    }
    image_references = dict(target.get("image_references", {}))

    catalogs = {}
    for catalog_id in PILOT_CATALOG_IDS:
        item = CatalogItem.model_validate(
            yaml.safe_load((root / "catalog" / catalog_id / "catalog-item.yaml").read_text())
        )
        request = LabRequest(
            tenant_id="static-preflight",
            requester_id="static-preflight",
            catalog_item_id=item.catalog_item_id,
            requested_mode=item.category,
        )
        adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
        adapter._overlay_path = "/not-used"
        adapter._target = type(
            "Target",
            (),
            {"cluster_id": "flightpath", "image_references": target.get("image_references", {})},
        )()
        # Node selection is a runtime capacity check, not part of source proof.
        adapter._select_workshop_node_name = lambda _request, _metadata: ""
        plan = adapter.create_plan(request, item)
        if plan.required_resources["workload_enabled"]:
            image = plan.required_resources["workload_helm_values"].get("image", {})
            image_references[f"{catalog_id}-workload"] = (
                f"{image.get('repository', '')}@{image.get('digest', '')}"
            )
        required_capabilities = set(item.required_capabilities)
        required_models = set(item.metadata.get("required_models", []))
        catalog_checks = {
            "operator_workshop": plan.required_resources["operator_workshop"] is True,
            "capabilities_declared": required_capabilities <= set(target.get("capabilities", [])),
            "model_routes_declared": required_models <= set(target.get("model_endpoints", {})),
            "no_internal_registry_grant_needed": (
                not adapter._requires_image_pull_grant(plan.required_resources)
            ),
        }
        catalogs[catalog_id] = {
            "checks": catalog_checks,
            "passed": all(catalog_checks.values()),
        }

    return {
        "schema": "launchpad.redhat.com/flightpath-execution-preflight/v1",
        "mutates_cluster": False,
        "source_checks": checks,
        "catalogs": catalogs,
        "static_contract_passed": all(checks.values())
        and all(result["passed"] for result in catalogs.values()),
        "runtime_proof": {
            "image_pull": "not_run",
            "model_call": "not_run",
            "showroom_and_workspace": "not_run",
            "reclaim_zero_residue": "not_run",
        },
        "image_references": image_references,
    }


def probe_registry_manifests(image_references: dict[str, str], opener=urlopen) -> dict:
    """Check anonymous HTTPS manifest HEAD only; never claim a cluster pull."""
    results = {}
    for name, reference in sorted(image_references.items()):
        check = {"reference": reference, "passed": False}
        try:
            if not re.fullmatch(r"quay\.io/[a-zA-Z0-9._/-]+@sha256:[0-9a-f]{64}", reference):
                raise ValueError("not a pinned Quay digest reference")
            repository, digest = reference.removeprefix("quay.io/").split("@", 1)
            url = f"https://quay.io/v2/{repository}/manifests/{digest}"
            request = Request(url, method="HEAD")
            with opener(request, timeout=15) as response:
                observed = response.headers.get("Docker-Content-Digest", "")
                check["http_status"] = response.status
                check["observed_digest"] = observed
                check["passed"] = response.status == 200 and observed == digest
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            check["error_type"] = type(exc).__name__
        results[name] = check
    return {
        "origin": "local-machine-anonymous-https",
        "proves_cluster_layer_pull": False,
        "passed": bool(results) and all(item["passed"] for item in results.values()),
        "images": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe-registry",
        action="store_true",
        help="make anonymous read-only HEAD requests for configured Quay manifest digests",
    )
    args = parser.parse_args()
    report = evaluate()
    if args.probe_registry:
        report["registry_manifest_probe"] = probe_registry_manifests(report["image_references"])
    print(json.dumps(report, indent=2, sort_keys=True))
    passed = report["static_contract_passed"] and (
        not args.probe_registry or report["registry_manifest_probe"]["passed"]
    )
    raise SystemExit(0 if passed else 1)
