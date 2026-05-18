from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

from app.adapters.interfaces import ProvisionResult
from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep

DEPLOY_ROOT = Path(__file__).resolve().parents[5] / "deploy" / "launchpad"
KUSTOMIZE_OVERLAY = DEPLOY_ROOT / "overlays" / "infra01"

WAIT_TIMEOUT = "300s"
HEALTH_TIMEOUT = 120
HEALTH_INTERVAL = 5


class OpenShiftProvisioningAdapter:
    def __init__(self, overlay_path: Optional[Path] = None):
        self._overlay_path = overlay_path or KUSTOMIZE_OVERLAY

    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        demo_source = catalog_item.metadata.get("demo_source", "launchpad")
        namespace = f"launchpad-{request.tenant_id}-{uuid.uuid4().hex[:8]}"

        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=namespace,
            steps=[
                ProvisioningStep(
                    name="create-project",
                    adapter="openshift",
                    action="oc_new_project",
                    params={"namespace": namespace},
                    order=1,
                ),
                ProvisioningStep(
                    name="apply-kustomize",
                    adapter="openshift",
                    action="oc_apply_kustomize",
                    params={
                        "overlay": str(self._overlay_path),
                        "namespace": namespace,
                    },
                    order=2,
                ),
                ProvisioningStep(
                    name="wait-for-pods",
                    adapter="openshift",
                    action="oc_wait_pods",
                    params={"namespace": namespace, "timeout": WAIT_TIMEOUT},
                    order=3,
                ),
                ProvisioningStep(
                    name="get-routes",
                    adapter="openshift",
                    action="oc_get_routes",
                    params={"namespace": namespace},
                    order=4,
                ),
            ],
            adapters_required=["openshift"],
            validation_steps=["pod-status", "route-accessible"],
            estimated_duration="120s",
            required_resources={
                "demo_source": demo_source,
                "overlay_path": str(self._overlay_path),
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        namespace = plan.target_namespace
        if not namespace:
            namespace = f"launchpad-demo-{uuid.uuid4().hex[:8]}"

        overlay_path = plan.required_resources.get("overlay_path", str(self._overlay_path))

        self._run_oc(["oc", "new-project", namespace, "--skip-config-write"])

        self._run_oc([
            "oc", "apply", "-k", overlay_path, "-n", namespace,
        ])

        self._run_oc([
            "oc", "wait", "--for=condition=Available",
            "deployment/backend", "deployment/partner-portal", "deployment/admin",
            "-n", namespace,
            f"--timeout={WAIT_TIMEOUT}",
        ])

        routes = self._get_routes(namespace)

        lab_url = routes.get("launchpad", f"https://launchpad-{namespace}.apps.cluster.local")
        api_url = routes.get("launchpad-api", f"https://launchpad-api-{namespace}.apps.cluster.local")

        return ProvisionResult(
            namespace=namespace,
            lab_url=lab_url,
            dashboard_url=api_url,
            resources={
                "namespace": namespace,
                "overlay_path": overlay_path,
                "routes": routes,
                "services": ["postgres", "backend", "partner-portal", "admin"],
            },
        )

    def _get_routes(self, namespace: str) -> dict[str, str]:
        result = self._run_oc([
            "oc", "get", "route", "-n", namespace,
            "-o", "jsonpath={range .items[*]}{.metadata.name}={.spec.host}{\"\\n\"}{end}",
        ])
        routes: dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            if "=" in line:
                name, host = line.split("=", 1)
                routes[name] = f"https://{host}"
        return routes

    def _run_oc(self, cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"oc command failed: {' '.join(cmd)}\n"
                f"stderr: {result.stderr}\n"
                f"stdout: {result.stdout}"
            )
        return result
