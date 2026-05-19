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

_CONTAINER_DEMOS = Path("/opt/demos-deploy/cluster")
_LOCAL_DEMOS = Path(__file__).resolve().parents[5] / "demos" / "deploy" / "cluster"
DEMO_DEPLOY_ROOT = _CONTAINER_DEMOS if _CONTAINER_DEMOS.exists() else _LOCAL_DEMOS

WAIT_TIMEOUT = 300  # seconds
POLL_INTERVAL = 5
HEALTH_TIMEOUT = 120
HEALTH_INTERVAL = 5

WATCHED_DEPLOYMENTS = ["backend", "partner-portal", "admin"]


class OpenShiftProvisioningAdapter:
    def __init__(self, overlay_path: Optional[Path] = None):
        self._overlay_path = overlay_path or DEMO_DEPLOY_ROOT
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
        meta = catalog_item.metadata or {}
        demo_source = meta.get("demo_source", "launchpad")
        deploy_method = meta.get("deploy_method", "kustomize-dir")
        deploy_path = meta.get("deploy_path", str(DEMO_DEPLOY_ROOT))
        namespace = f"launchpad-{request.tenant_id}-{uuid.uuid4().hex[:8]}"

        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=namespace,
            steps=[
                ProvisioningStep(name="create-project", adapter="openshift", action="create_namespace", order=1),
                ProvisioningStep(name="deploy", adapter="openshift", action="deploy", order=2),
                ProvisioningStep(name="get-routes", adapter="openshift", action="get_routes", order=3),
            ],
            adapters_required=["openshift"],
            validation_steps=["pod-status", "route-accessible"],
            estimated_duration="120s",
            required_resources={
                "demo_source": demo_source,
                "deploy_method": deploy_method,
                "deploy_path": deploy_path,
                "overlay_path": str(self._overlay_path),
                "catalog_item_id": catalog_item.catalog_item_id,
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        namespace = plan.target_namespace
        if not namespace:
            namespace = f"launchpad-demo-{uuid.uuid4().hex[:8]}"

        res = plan.required_resources
        deploy_method = res.get("deploy_method", "kustomize-dir")
        deploy_path = res.get("deploy_path", str(self._overlay_path))

        # Resolve deploy path for container context
        resolved_path = deploy_path
        if "demos/quickstarts/" in deploy_path:
            resolved_path = deploy_path.replace("demos/quickstarts/", "/opt/quickstarts/")
        elif "demos/deploy/" in deploy_path:
            resolved_path = deploy_path.replace("demos/deploy/", "/opt/demos-deploy/")
        if not Path(resolved_path).exists() and Path(deploy_path).exists():
            resolved_path = deploy_path

        # --- Step 1: Create namespace ---
        self._create_namespace(namespace)

        # --- Step 2: Grant image pull access ---
        self._grant_image_pull(namespace)

        # --- Step 3: Create secrets ---
        session_maas_key = res.get("maas_api_key", "")
        self._create_demo_secrets(namespace, session_maas_key)

        # --- Step 4: Deploy based on method ---
        if deploy_method == "helm":
            self._deploy_helm(resolved_path, namespace, res.get("catalog_item_id", "quickstart"))
        elif deploy_method == "kustomize":
            self._deploy_kustomize(resolved_path, namespace)
        else:
            self._apply_kustomize(str(DEMO_DEPLOY_ROOT), namespace)

        # --- Step 5: Brief wait for resources to be created (not full readiness) ---
        import time
        time.sleep(5)

        # --- Step 6: Retrieve routes ---
        routes = self._get_routes(namespace)

        route_names = list(routes.keys())
        lab_url = routes.get(route_names[0], f"https://{namespace}.apps.cluster.local") if route_names else f"https://{namespace}.apps.cluster.local"
        api_url = lab_url

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

    def _grant_image_pull(self, namespace: str) -> None:
        body = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(
                name=f"{namespace}-image-puller",
                namespace="partner-ai-launchpad",
            ),
            role_ref=client.V1RoleRef(
                api_group="rbac.authorization.k8s.io",
                kind="ClusterRole",
                name="system:image-puller",
            ),
            subjects=[
                client.RbacV1Subject(
                    kind="Group",
                    name=f"system:serviceaccounts:{namespace}",
                    api_group="rbac.authorization.k8s.io",
                )
            ],
        )
        try:
            self._rbac_v1 = client.RbacAuthorizationV1Api()
            self._rbac_v1.create_namespaced_role_binding(
                namespace="partner-ai-launchpad", body=body
            )
        except ApiException as exc:
            if exc.status != 409:
                pass

    def _create_demo_secrets(self, namespace: str, session_maas_key: str = "") -> None:
        import os
        litellm_key = session_maas_key or os.environ.get("LITELLM_API_KEY", "")
        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(name="gateway-config"),
            string_data={
                "LITELLM_API_BASE": os.environ.get(
                    "LITELLM_API_BASE",
                    "https://litellm-prod.apps.maas.redhatworkshops.io",
                ),
                "LITELLM_API_KEY": litellm_key,
                "API_KEY": "",
                "LOCAL_FALLBACK_ENABLED": "true",
                "MAAS_SESSION_KEY": session_maas_key,
            },
        )
        try:
            self._core_v1.create_namespaced_secret(namespace, secret)
        except ApiException as exc:
            if exc.status != 409:
                pass

        pg_secret = client.V1Secret(
            metadata=client.V1ObjectMeta(name="postgres-credentials"),
            string_data={
                "POSTGRES_DB": "inference_platform",
                "POSTGRES_USER": "gateway",
                "POSTGRES_PASSWORD": f"lab-{namespace[:16]}",
                "DATABASE_URL": f"postgresql://gateway:lab-{namespace[:16]}@postgres:5432/inference_platform",
            },
        )
        try:
            self._core_v1.create_namespaced_secret(namespace, pg_secret)
        except ApiException as exc:
            if exc.status != 409:
                pass

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

    def _deploy_helm(self, chart_path: str, namespace: str, release_name: str) -> None:
        helm = shutil.which("helm")
        if helm is None:
            raise ValueError("'helm' not found on PATH")

        dep_result = subprocess.run(
            [helm, "dependency", "build", chart_path],
            capture_output=True, text=True, timeout=120,
        )

        result = subprocess.run(
            [helm, "install", release_name, chart_path, "-n", namespace, "--timeout", "120s"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise ValueError(f"Helm install failed for '{release_name}' in '{namespace}':\n{result.stderr[:300]}")

    def _deploy_kustomize(self, kustomize_path: str, namespace: str) -> None:
        kubectl = shutil.which("kubectl") or shutil.which("oc")
        if kubectl is None:
            raise ValueError("Neither 'kubectl' nor 'oc' found on PATH")

        result = subprocess.run(
            [kubectl, "apply", "-k", kustomize_path, "-n", namespace],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise ValueError(f"Kustomize apply failed in '{namespace}':\n{result.stderr[:300]}")

    def _apply_kustomize(self, overlay_path: str, namespace: str) -> None:
        kubectl = shutil.which("kubectl") or shutil.which("oc")
        if kubectl is None:
            raise ValueError(
                "Neither 'kubectl' nor 'oc' found on PATH. "
                "One of them is required to apply manifests."
            )

        deploy_dir = Path(overlay_path)
        skip_files = {"namespace.yaml", "kustomization.yaml", "secrets-template.yaml", "keycloak-realm.yaml", "oauth-proxy.yaml", "postgres-backup.yaml", "frontend-deployment.yaml"}
        yamls = sorted([
            f for f in deploy_dir.glob("*.yaml")
            if f.name not in skip_files
        ])

        if not yamls:
            raise ValueError(f"No YAML files found in {overlay_path}")

        for yaml_file in yamls:
            content = yaml_file.read_text()
            cleaned = "\n".join(
                line for line in content.splitlines()
                if not line.strip().startswith("namespace:")
            )
            result = subprocess.run(
                [kubectl, "apply", "-f", "-", "-n", namespace],
                input=cleaned,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0 and "already exists" not in result.stderr:
                raise ValueError(
                    f"Failed to apply '{yaml_file.name}' "
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
