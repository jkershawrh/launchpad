from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
import yaml
from pathlib import Path
from typing import Optional

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException

    HAS_KUBERNETES = True
except ImportError:  # pragma: no cover
    HAS_KUBERNETES = False

from app.adapters.interfaces import ProvisionResult
from app.adapters.openshift.showroom_gitops import (
    ShowroomGitOpsAdapter,
    ShowroomSeat,
    build_showroom_application,
)
from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep

_CONTAINER_DEMOS = Path("/opt/demos-deploy/cluster")
_LOCAL_DEMOS = Path(__file__).resolve().parents[5] / "demos" / "deploy" / "cluster"
DEMO_DEPLOY_ROOT = _CONTAINER_DEMOS if _CONTAINER_DEMOS.exists() else _LOCAL_DEMOS

WAIT_TIMEOUT = 300  # seconds
POLL_INTERVAL = 5
HEALTH_TIMEOUT = 120
HEALTH_INTERVAL = 5

WATCHED_DEPLOYMENTS = ["backend", "partner-portal", "admin"]
logger = logging.getLogger("launchpad.openshift.provisioning")


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
        self._showroom_gitops = ShowroomGitOpsAdapter(
            self._custom_objects, os.environ.get("SHOWROOM_ARGOCD_NAMESPACE", "argocd")
        )

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
                "demo_pages": meta.get("demo_pages", "all"),
                "workspace_path": meta.get("workspace_path", ""),
                "showroom_enabled": bool(meta.get("showroom", False)),
                "showroom_title": meta.get("showroom_title", catalog_item.display_name),
                "showroom_steps": meta.get("showroom_steps", []),
                "workshop_id": request.metadata.get("workshop_id", request.request_id),
                "seat_id": request.metadata.get("seat_id", request.request_id),
                "participant_id": request.metadata.get("participant_id", request.requester_id),
                "showroom_content_repo_url": meta.get(
                    "showroom_content_repo_url",
                    os.environ.get("SHOWROOM_CONTENT_REPO_URL", "https://github.com/jkershawrh/launchpad.git"),
                ),
                "showroom_content_ref": meta.get(
                    "showroom_content_ref", os.environ.get("SHOWROOM_CONTENT_REF", "main")
                ),
                "showroom_content_playbook": meta.get("showroom_content_playbook", "site.yml"),
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        res = plan.required_resources
        res.get("deploy_method", "kustomize-dir")
        res.get("deploy_path", str(self._overlay_path))
        demo_pages = res.get("demo_pages", "all")
        catalog_item_id = res.get("catalog_item_id", "demo")
        showroom_enabled = bool(res.get("showroom_enabled", False))
        session_maas_key = res.get("maas_api_key", "")

        # Extract tenant from namespace name
        namespace = plan.target_namespace or f"launchpad-demo-{uuid.uuid4().hex[:8]}"
        # Parse tenant: launchpad-{tenant}-{hash}
        parts = namespace.split("-")
        tenant_id = "-".join(parts[1:-1]) if len(parts) > 2 else "default"
        gw_namespace = f"launchpad-gw-{tenant_id}"
        seat_id = str(res.get("seat_id", ""))
        # Keep the deterministic suffix at six characters so the generated
        # OpenShift Route host label remains within the 63-character limit.
        suffix = re.sub(r"[^a-z0-9]", "", seat_id.lower())[:6] if showroom_enabled and seat_id else uuid.uuid4().hex[:6]
        demo_namespace = self._demo_namespace(tenant_id, catalog_item_id, suffix or uuid.uuid4().hex[:6])

        # --- Step 1: Ensure tenant gateway exists ---
        gw_existed = self._namespace_exists(gw_namespace)
        if not gw_existed:
            self._create_namespace(gw_namespace)
            self._grant_image_pull(gw_namespace)
            self._create_demo_secrets(gw_namespace, session_maas_key)
            self._apply_kustomize(str(DEMO_DEPLOY_ROOT), gw_namespace)
            self._wait_for_deployments(
                gw_namespace, deployments={"postgres", "gateway"}
            )

        # --- Step 2: Create demo namespace ---
        self._create_namespace(
            demo_namespace,
            {"argocd.argoproj.io/managed-by": "argocd"} if showroom_enabled else None,
        )
        self._grant_image_pull(demo_namespace)
        # The official Showroom chart clones Git content and builds Antora at
        # startup. Keep the restricted egress policy for ordinary demos, but
        # do not attach it to guided Showroom namespaces.
        if not showroom_enabled:
            self._apply_network_policy(demo_namespace)

        # --- Step 3: Deploy filtered frontend in demo namespace ---
        gateway_url = f"http://gateway.{gw_namespace}.svc.cluster.local:8080"
        self._deploy_demo_frontend(demo_namespace, demo_pages, gateway_url, catalog_item_id)

        time.sleep(5)

        # --- Step 4: Retrieve routes from demo namespace ---
        routes = self._get_routes(demo_namespace)
        workspace_url = self._workspace_url(
            routes.get("demo", ""), res.get("workspace_path", "")
        )

        if showroom_enabled:
            apps_domain = os.environ.get("OPENSHIFT_APPS_DOMAIN", "apps.oberon.fm2aihpcsed.com")
            showroom_app = build_showroom_application(
                ShowroomSeat(
                    namespace=demo_namespace,
                    workshop_id=str(res.get("workshop_id", plan.request_id)),
                    seat_id=str(res.get("seat_id", plan.request_id)),
                    participant_id=str(res.get("participant_id", "lab-user")),
                    workspace_url=workspace_url,
                    content_repo_url=str(res["showroom_content_repo_url"]),
                    content_ref=str(res["showroom_content_ref"]),
                    apps_domain=apps_domain,
                    console_url=os.environ.get("OPENSHIFT_CONSOLE_URL", ""),
                    content_playbook=str(res.get("showroom_content_playbook", "site.yml")),
                ),
                argocd_namespace=os.environ.get("SHOWROOM_ARGOCD_NAMESPACE", "argocd"),
                argocd_project=os.environ.get("SHOWROOM_ARGOCD_PROJECT", "default"),
                chart_version=os.environ.get("SHOWROOM_CHART_VERSION", "2.2.*"),
            )
            self._showroom_gitops.apply(showroom_app)
            routes = self._wait_for_showroom_route(demo_namespace)

        route_names = list(routes.keys())
        fallback_url = f"https://{demo_namespace}.apps.cluster.local"
        lab_url = routes.get("showroom") or routes.get("showroom-proxy") or routes.get("demo") or (routes.get(route_names[0]) if route_names else fallback_url)

        self._active_namespaces[demo_namespace] = gw_namespace

        return ProvisionResult(
            namespace=demo_namespace,
            lab_url=lab_url,
            dashboard_url=f"https://{gw_namespace}.apps.cluster.local",
            resources={
                "namespace": demo_namespace,
                "gateway_namespace": gw_namespace,
                "demo_pages": demo_pages,
                "catalog_item_id": catalog_item_id,
                "routes": routes,
                "showroom_url": routes.get("showroom") or routes.get("showroom-proxy"),
                "showroom_application": showroom_app["metadata"]["name"] if showroom_enabled else None,
                "workspace_url": workspace_url,
                "gateway_url": gateway_url,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _namespace_exists(self, namespace: str) -> bool:
        try:
            self._core_v1.read_namespace(namespace)
            return True
        except ApiException:
            return False

    def _deploy_demo_frontend(self, namespace: str, pages: str, gateway_url: str, demo_name: str) -> None:
        gateway = gateway_url.removeprefix("http://").removeprefix("https://")
        gw_host, _, gw_port = gateway.partition(":")
        gw_port = gw_port or "8080"
        dns_resolver = "172.30.0.10"
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as resolv_conf:
                dns_resolver = next(
                    line.split()[1]
                    for line in resolv_conf
                    if line.startswith("nameserver ")
                )
        except (OSError, StopIteration, IndexError):
            pass

        nginx_conf = f"""worker_processes auto;
error_log /dev/stderr;
pid /tmp/nginx.pid;
events {{ worker_connections 1024; }}
http {{
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    resolver {dns_resolver} valid=10s;
    server {{
        listen 8080;
        root /opt/app-root/src;
        index index.html;
        set $gateway {gw_host};
        location /v1/ {{
            proxy_pass http://$gateway:{gw_port}/v1/;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 300s;
        }}
        location /api/ {{
            proxy_pass http://$gateway:{gw_port}/api/;
            proxy_set_header Host $host;
            proxy_read_timeout 300s;
        }}
        location / {{
            try_files $uri $uri/ /index.html;
        }}
    }}
}}"""

        config_data = {
            "config.json": json.dumps({
                "pages": [pages] if isinstance(pages, str) else pages,
                "gateway_url": gateway_url,
                "demo_name": demo_name,
            }),
            "nginx.conf": nginx_conf,
        }
        try:
            self._core_v1.create_namespaced_config_map(namespace, client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name="demo-config"),
                data=config_data,
            ))
        except ApiException as e:
            if e.status != 409:
                pass

        FRONTEND_IMAGE = "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/inference-frontend:latest"

        container = client.V1Container(
            name="frontend",
            image=FRONTEND_IMAGE,
            ports=[client.V1ContainerPort(container_port=8080)],
            volume_mounts=[
                client.V1VolumeMount(name="config", mount_path="/opt/app-root/src/config.json", sub_path="config.json"),
                client.V1VolumeMount(name="config", mount_path="/etc/nginx/nginx.conf", sub_path="nginx.conf"),
            ],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "100m", "memory": "128Mi"},
                limits={"cpu": "500m", "memory": "256Mi"},
            ),
        )

        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(name="demo-frontend", labels={"app": "demo-frontend"}),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": "demo-frontend"}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "demo-frontend"}),
                    spec=client.V1PodSpec(
                        containers=[container],
                        volumes=[
                            client.V1Volume(name="config", config_map=client.V1ConfigMapVolumeSource(name="demo-config")),
                        ],
                    ),
                ),
            ),
        )

        try:
            self._apps_v1.create_namespaced_deployment(namespace, deployment)
        except ApiException as e:
            if e.status != 409:
                pass

        try:
            self._core_v1.create_namespaced_service(namespace, client.V1Service(
                metadata=client.V1ObjectMeta(name="demo-frontend"),
                spec=client.V1ServiceSpec(
                    selector={"app": "demo-frontend"},
                    ports=[client.V1ServicePort(name="http", port=8080, target_port=8080)],
                ),
            ))
        except ApiException as e:
            if e.status != 409:
                pass

        oc = shutil.which("oc") or shutil.which("kubectl")
        if oc:
            subprocess.run(
                [oc, "create", "route", "edge", "demo", "--service=demo-frontend", "--port=8080", "-n", namespace],
                capture_output=True, text=True, timeout=30,
            )

    @staticmethod
    def _workspace_url(base_url: str, workspace_path: str) -> str:
        if not base_url:
            return ""
        path = str(workspace_path or "").strip()
        if not path:
            return base_url
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _wait_for_showroom_route(self, namespace: str) -> dict[str, str]:
        """Wait for Argo CD to sync far enough for the chart route to exist."""
        timeout = int(os.environ.get("SHOWROOM_ROUTE_TIMEOUT", "300"))
        deadline = time.time() + timeout
        routes: dict[str, str] = {}
        while time.time() < deadline:
            routes = self._get_routes(namespace)
            if routes.get("showroom") or routes.get("showroom-proxy"):
                return routes
            time.sleep(HEALTH_INTERVAL)
        raise ValueError(
            f"Showroom route was not created in namespace '{namespace}' within {timeout}s"
        )

    @staticmethod
    def _demo_namespace(tenant_id: str, catalog_item_id: str, suffix: str) -> str:
        def slug(value: str) -> str:
            return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")

        tenant = slug(tenant_id)[:18].rstrip("-") or "tenant"
        catalog = slug(catalog_item_id)[:18].rstrip("-") or "lab"
        return f"launchpad-{tenant}-{catalog}-{suffix}"

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
                    "",
                ),
                "LITELLM_API_KEY": litellm_key,
                "API_KEY": "",
                "LOCAL_FALLBACK_ENABLED": "false",
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

    def _create_namespace(self, namespace: str, extra_labels: dict = None) -> None:
        labels = {
            "app.kubernetes.io/part-of": "launchpad",
            "app.kubernetes.io/managed-by": "launchpad",
            "pod-security.kubernetes.io/enforce": "restricted",
            "pod-security.kubernetes.io/warn": "restricted",
        }
        if extra_labels:
            labels.update(extra_labels)
        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace, labels=labels)
        )
        try:
            self._core_v1.create_namespace(body=body)
        except ApiException as exc:
            if exc.status == 409:
                pass
            else:
                raise ValueError(
                    f"Failed to create namespace '{namespace}': {exc.status} {exc.reason}"
                ) from exc

    @staticmethod
    def _build_demo_network_policy(namespace: str) -> dict:
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": "demo-egress-restrict",
                "namespace": namespace,
            },
            "spec": {
                "podSelector": {},
                "policyTypes": ["Egress"],
                "egress": [
                    {
                        "to": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "kubernetes.io/metadata.name": "intel-inference",
                                    }
                                }
                            }
                        ],
                        "ports": [
                            {"protocol": "TCP", "port": 4000},
                        ],
                    },
                    {
                        "ports": [
                            {"protocol": "UDP", "port": 53},
                            {"protocol": "TCP", "port": 53},
                        ],
                    },
                ],
            },
        }

    def _apply_network_policy(self, namespace: str) -> None:
        policy = self._build_demo_network_policy(namespace)
        try:
            from kubernetes import client as k8s_client
            net_v1 = k8s_client.NetworkingV1Api()
            net_v1.create_namespaced_network_policy(namespace=namespace, body=policy)
        except Exception as e:
            logger.warning("Failed to create NetworkPolicy in %s: %s", namespace, e)

    def _deploy_helm(self, chart_path: str, namespace: str, release_name: str) -> None:
        helm = shutil.which("helm")
        if helm is None:
            raise ValueError("'helm' not found on PATH")

        subprocess.run(
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
            cleaned = self._inject_storage_class(
                cleaned,
                os.environ.get("DEMO_STORAGE_CLASS")
                or os.environ.get("SANDBOX_STORAGE_CLASS", ""),
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

    @staticmethod
    def _inject_storage_class(content: str, storage_class: str) -> str:
        if not storage_class:
            return content
        documents = list(yaml.safe_load_all(content))
        changed = False
        for document in documents:
            if not isinstance(document, dict) or document.get("kind") != "PersistentVolumeClaim":
                continue
            spec = document.setdefault("spec", {})
            if not spec.get("storageClassName"):
                spec["storageClassName"] = storage_class
                changed = True
        return yaml.safe_dump_all(documents, sort_keys=False) if changed else content

    def _wait_for_deployments(
        self,
        namespace: str,
        timeout: int = WAIT_TIMEOUT,
        deployments: set[str] | None = None,
    ) -> None:
        deadline = time.time() + timeout
        pending = set(deployments or WATCHED_DEPLOYMENTS)

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
