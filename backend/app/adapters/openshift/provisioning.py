from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException

    HAS_KUBERNETES = True
except ImportError:  # pragma: no cover
    HAS_KUBERNETES = False

from app.adapters.interfaces import ProvisionResult
from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep

DEPLOY_ROOT = Path(__file__).resolve().parents[5] / "deploy" / "launchpad"
KUSTOMIZE_OVERLAY = DEPLOY_ROOT / "overlays" / "infra01"

WAIT_TIMEOUT = 300  # seconds
POLL_INTERVAL = 5
HEALTH_TIMEOUT = 120
HEALTH_INTERVAL = 5

WATCHED_DEPLOYMENTS = ["backend", "partner-portal", "admin"]


class OpenShiftProvisioningAdapter:
    def __init__(self, overlay_path: Optional[Path] = None):
        self._overlay_path = overlay_path or KUSTOMIZE_OVERLAY
        self._active_namespaces: dict[str, str] = {}

        if not HAS_KUBERNETES:
            raise ValueError(
                "The 'kubernetes' Python package is required for OpenShiftProvisioningAdapter. "
                "Install it with: pip install kubernetes"
            )

        try:
            config.load_incluster_config()
        except config.ConfigException:
            try:
                config.load_kube_config()
            except config.ConfigException as exc:
                raise ValueError(
                    f"Unable to load Kubernetes configuration (tried in-cluster and kubeconfig): {exc}"
                ) from exc

        self._core_v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()
        self._custom_objects = client.CustomObjectsApi()

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
                    action="create_namespace",
                    params={"namespace": namespace},
                    order=1,
                ),
                ProvisioningStep(
                    name="apply-kustomize",
                    adapter="openshift",
                    action="apply_kustomize",
                    params={
                        "overlay": str(self._overlay_path),
                        "namespace": namespace,
                    },
                    order=2,
                ),
                ProvisioningStep(
                    name="wait-for-deployments",
                    adapter="openshift",
                    action="wait_deployments",
                    params={"namespace": namespace, "timeout": WAIT_TIMEOUT},
                    order=3,
                ),
                ProvisioningStep(
                    name="get-routes",
                    adapter="openshift",
                    action="get_routes",
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

        # --- Step 1: Create namespace ---
        self._create_namespace(namespace)

        # --- Step 2: Apply kustomize overlay ---
        self._apply_kustomize(overlay_path, namespace)

        # --- Step 3: Wait for deployments to become available ---
        self._wait_for_deployments(namespace, WAIT_TIMEOUT)

        # --- Step 4: Retrieve routes ---
        routes = self._get_routes(namespace)

        lab_url = routes.get("launchpad", f"https://launchpad-{namespace}.apps.cluster.local")
        api_url = routes.get(
            "launchpad-api", f"https://launchpad-api-{namespace}.apps.cluster.local"
        )

        self._active_namespaces[namespace] = overlay_path

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_namespace(self, namespace: str) -> None:
        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace)
        )
        try:
            self._core_v1.create_namespace(body=body)
        except ApiException as exc:
            if exc.status == 409:
                # Namespace already exists – treat as success
                pass
            else:
                raise ValueError(
                    f"Failed to create namespace '{namespace}': {exc.status} {exc.reason}"
                ) from exc

    def _apply_kustomize(self, overlay_path: str, namespace: str) -> None:
        kubectl = shutil.which("kubectl") or shutil.which("oc")
        if kubectl is None:
            raise ValueError(
                "Neither 'kubectl' nor 'oc' found on PATH. "
                "One of them is required to apply kustomize overlays."
            )

        result = subprocess.run(
            [kubectl, "apply", "-k", overlay_path, "-n", namespace],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise ValueError(
                f"Failed to apply kustomize overlay '{overlay_path}' "
                f"in namespace '{namespace}':\n{result.stderr}"
            )

    def _wait_for_deployments(
        self,
        namespace: str,
        timeout: int = WAIT_TIMEOUT,
    ) -> None:
        deadline = time.time() + timeout
        pending = set(WATCHED_DEPLOYMENTS)

        while pending and time.time() < deadline:
            for name in list(pending):
                try:
                    dep = self._apps_v1.read_namespaced_deployment(name, namespace)
                    available = dep.status.available_replicas or 0
                    if available >= 1:
                        pending.discard(name)
                except ApiException as exc:
                    if exc.status == 404:
                        # Deployment not created yet – keep waiting
                        pass
                    else:
                        raise ValueError(
                            f"Error checking deployment '{name}' in '{namespace}': "
                            f"{exc.status} {exc.reason}"
                        ) from exc

            if pending:
                time.sleep(POLL_INTERVAL)

        if pending:
            raise ValueError(
                f"Timed out after {timeout}s waiting for deployments in '{namespace}': "
                f"{', '.join(sorted(pending))}"
            )

    def _get_routes(self, namespace: str) -> dict[str, str]:
        try:
            route_list = self._custom_objects.list_namespaced_custom_object(
                group="route.openshift.io",
                version="v1",
                namespace=namespace,
                plural="routes",
            )
        except ApiException as exc:
            raise ValueError(
                f"Failed to list routes in namespace '{namespace}': {exc.status} {exc.reason}"
            ) from exc

        routes: dict[str, str] = {}
        for item in route_list.get("items", []):
            name = item.get("metadata", {}).get("name", "")
            host = item.get("spec", {}).get("host", "")
            if name and host:
                tls = item.get("spec", {}).get("tls")
                scheme = "https" if tls else "http"
                routes[name] = f"{scheme}://{host}"
        return routes
