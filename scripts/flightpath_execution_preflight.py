"""Read-only source preflight for Flightpath execution-seat certification.

No cluster API calls, image pulls, DNS probes, orders, or mutations occur here.
The report deliberately leaves runtime proof open.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
    }


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["static_contract_passed"] else 1)
