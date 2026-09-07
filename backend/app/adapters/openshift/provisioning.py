from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import requests
import yaml

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException

    HAS_KUBERNETES = True
except ImportError:  # pragma: no cover
    HAS_KUBERNETES = False

from app.adapters.interfaces import ProvisionResult
from app.adapters.openshift.showroom_gitops import (
    SHOWROOM_GIT_CLONER_IMAGE,
    SHOWROOM_RUNTIME_SECRET_NAME,
    SHOWROOM_TERMINAL_IMAGE,
    ShowroomGitOpsAdapter,
    ShowroomSeat,
    ShowroomToolTab,
    build_showroom_application,
)
from app.adapters.openshift.workload_gitops import (
    WorkloadGitOpsAdapter,
    WorkloadSeat,
    build_runtime_secret,
    build_workload_application,
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
    def __init__(
        self,
        overlay_path: Path | None = None,
        *,
        clients=None,
        target=None,
        argocd_custom_objects=None,
        control_core=None,
    ):
        self._overlay_path = overlay_path or DEMO_DEPLOY_ROOT
        self._active_namespaces: dict[str, str] = {}
        self._gateway_bootstrap_lock = threading.Lock()

        if not HAS_KUBERNETES:
            raise ValueError(
                "The 'kubernetes' Python package is required for OpenShiftProvisioningAdapter. "
                "Install it with: pip install kubernetes"
            )

        self._target = target
        if clients is None:
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
            self._rbac_v1 = client.RbacAuthorizationV1Api()
        else:
            self._core_v1 = clients.core
            self._apps_v1 = clients.apps
            self._custom_objects = clients.custom
            self._rbac_v1 = clients.rbac
        self._control_core_v1 = control_core or self._core_v1
        self._showroom_gitops = ShowroomGitOpsAdapter(
            argocd_custom_objects or self._custom_objects,
            os.environ.get("SHOWROOM_ARGOCD_NAMESPACE", "argocd"),
        )
        self._workload_gitops = WorkloadGitOpsAdapter(
            argocd_custom_objects or self._custom_objects,
            os.environ.get("SHOWROOM_ARGOCD_NAMESPACE", "argocd"),
        )

    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        meta = catalog_item.metadata or {}
        demo_source = meta.get("demo_source", "launchpad")
        deploy_method = meta.get("deploy_method", "kustomize-dir")
        deploy_path = meta.get("deploy_path", str(DEMO_DEPLOY_ROOT))
        workshop_node_name = self._select_workshop_node_name(request, meta)
        seat_ref = str(request.metadata.get("seat_id") or request.request_id)
        suffix = re.sub(r"[^a-z0-9]", "", seat_ref.lower())[:6]
        namespace = self._demo_namespace(
            request.tenant_id,
            str(meta.get("namespace_slug") or catalog_item.catalog_item_id),
            suffix or uuid.uuid4().hex[:6],
        )

        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=namespace,
            target_cluster=(
                getattr(self, "_target", None).cluster_id
                if getattr(self, "_target", None)
                else request.metadata.get("target_cluster")
            ),
            steps=[
                ProvisioningStep(
                    name="create-project", adapter="openshift", action="create_namespace", order=1
                ),
                ProvisioningStep(name="deploy", adapter="openshift", action="deploy", order=2),
                ProvisioningStep(
                    name="get-routes", adapter="openshift", action="get_routes", order=3
                ),
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
                "tenant_id": request.tenant_id,
                "demo_pages": meta.get("demo_pages", "all"),
                "workspace_path": meta.get("workspace_path", ""),
                "workspace_route_name": meta.get("workspace_route_name", ""),
                "workspace_title": meta.get("workspace_title", "RAG Workspace"),
                "showroom_enabled": bool(meta.get("showroom", False)),
                "showroom_title": meta.get("showroom_title", catalog_item.display_name),
                "showroom_steps": meta.get("showroom_steps", []),
                "showroom_journey": meta.get("showroom_journey", "guided-rag"),
                "operator_workshop": bool(meta.get("operator_workshop", False)),
                "workshop_node_name": workshop_node_name,
                "content_only": bool(meta.get("content_only", False)),
                "workshop_id": request.metadata.get("workshop_id", request.request_id),
                "seat_id": request.metadata.get("seat_id", request.request_id),
                "participant_id": request.metadata.get("participant_id", request.requester_id),
                "required_capabilities": list(catalog_item.required_capabilities),
                "showroom_content_repo_url": meta.get(
                    "showroom_content_repo_url",
                    os.environ.get(
                        "SHOWROOM_CONTENT_REPO_URL", "https://github.com/rhpds/launchpad.git"
                    ),
                ),
                "showroom_content_ref": meta.get(
                    "showroom_content_ref", os.environ.get("SHOWROOM_CONTENT_REF", "main")
                ),
                "showroom_content_playbook": meta.get("showroom_content_playbook", "site.yml"),
                "showroom_tabs": meta.get("showroom_tabs", []),
                "showroom_support_images": dict(
                    getattr(getattr(self, "_target", None), "image_references", {})
                ),
                "workload_enabled": "helm-workload" in catalog_item.provisioner_refs,
                "workload_gitops_ready": bool(meta.get("workload_gitops_ready", False)),
                "workload_repo": meta.get("workload_repo", ""),
                "workload_revision": meta.get("workload_revision", ""),
                "workload_deploy_path": meta.get("workload_deploy_path", ""),
                "workload_release_name": meta.get("workload_release_name", "workload"),
                "workload_helm_values": meta.get("workload_helm_values", {}),
                "workload_ignore_differences": meta.get(
                    "workload_ignore_differences", []
                ),
                "workload_runtime_secret_name": meta.get("workload_runtime_secret_name", ""),
                "workload_runtime_secret_sources": meta.get("workload_runtime_secret_sources", {}),
                "workload_runtime_secret_value_path": meta.get(
                    "workload_runtime_secret_value_path", ""
                ),
                "workload_identity_value_path": meta.get("workload_identity_value_path", ""),
                "workload_routes": meta.get("workload_routes", {}),
                "workload_readiness": meta.get("workload_readiness", []),
            },
        )

    @staticmethod
    def _showroom_maas_endpoint(resources: dict) -> str:
        """Return the selected cluster model base without the OpenAI `/v1` suffix."""
        endpoint = str(
            resources.get("maas_endpoint") or os.environ.get("LITELLM_API_BASE", "")
        ).rstrip("/")
        return endpoint.removesuffix("/v1")

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        res = plan.required_resources
        res.get("deploy_method", "kustomize-dir")
        res.get("deploy_path", str(self._overlay_path))
        demo_pages = res.get("demo_pages", "all")
        catalog_item_id = res.get("catalog_item_id", "demo")
        showroom_enabled = bool(res.get("showroom_enabled", False))
        operator_workshop = bool(res.get("operator_workshop", False))
        workload_enabled = bool(res.get("workload_enabled", False))
        session_maas_key = res.get("maas_api_key", "")

        # Intake-managed workloads remain fail closed until their application-
        # specific Secret, route, RBAC, readiness, and cleanup contract has
        # passed certification. This check intentionally happens before the
        # first cluster mutation.
        if workload_enabled and not res.get("workload_gitops_ready", False):
            raise ValueError(
                "Catalog workload is not activation-ready; complete its GitOps "
                "runtime contract and certification first"
            )

        namespace = plan.target_namespace or f"launchpad-demo-{uuid.uuid4().hex[:8]}"
        tenant_id = str(res.get("tenant_id") or "default")
        gw_namespace = f"launchpad-gw-{tenant_id}"
        # The final target is selected by create_plan and persisted on the
        # session before this method performs any cluster mutation. Never
        # generate a second namespace here: cleanup and retry must target the
        # exact same object after an interrupted process.
        demo_namespace = namespace

        # --- Step 1: Ensure tenant gateway exists ---
        if not operator_workshop:
            with self._gateway_bootstrap_lock:
                gw_existed = self._namespace_exists(gw_namespace)
                if not gw_existed:
                    self._create_namespace(gw_namespace)
                    self._grant_image_pull(gw_namespace)
                    self._create_demo_secrets(gw_namespace, session_maas_key)
                    self._apply_kustomize(str(DEMO_DEPLOY_ROOT), gw_namespace)
                    self._wait_for_deployments(gw_namespace, deployments={"postgres", "gateway"})

        # --- Step 2: Create demo namespace ---
        self._create_namespace(
            demo_namespace,
            {
                **({"argocd.argoproj.io/managed-by": "argocd"} if showroom_enabled else {}),
                "launchpad.redhat.com/session-id": str(res.get("session_id", plan.request_id)),
                "launchpad.redhat.com/request-id": plan.request_id,
                "launchpad.redhat.com/workshop-id": str(res.get("workshop_id", "")),
                "launchpad.redhat.com/seat-id": str(res.get("seat_id", "")),
                "launchpad.redhat.com/tenant": tenant_id,
                "launchpad.redhat.com/cluster-id": plan.target_cluster or "oberon",
            },
            (
                {
                    "openshift.io/node-selector": (
                        f"kubernetes.io/hostname={res['workshop_node_name']}"
                    )
                }
                if res.get("workshop_node_name")
                else None
            ),
        )
        self._grant_image_pull(demo_namespace)
        self._grant_participant_access(
            demo_namespace,
            str(res.get("participant_id", "")),
            grant_application_logs="openshift_logging" in set(res.get("required_capabilities", [])),
        )
        requested_models = list(res.get("requested_models", []))
        # Model-backed workloads mount the same trust bundle on every target.
        # Copy it even when a cluster currently resolves its model through an
        # internal HTTP Service so the manifest is portable to a verified
        # HTTPS route without a cluster-specific volume contract.
        if requested_models:
            self._apply_model_ca_bundle(
                demo_namespace,
                resources=res,
                cluster_id=plan.target_cluster or "oberon",
            )
        maas_endpoint = self._showroom_maas_endpoint(res)
        if showroom_enabled:
            # Participant credentials are written directly to a namespaced
            # Secret. They must never be serialized into the Argo CD
            # Application that deploys Showroom.
            self._apply_showroom_runtime_secret(
                namespace=demo_namespace,
                resources={**res, "tenant_id": tenant_id},
                cluster_id=plan.target_cluster or "oberon",
            )
        # The official Showroom chart clones Git content and builds Antora at
        # startup. Keep the restricted egress policy for ordinary demos, but
        # do not attach it to guided Showroom namespaces.
        if not showroom_enabled:
            self._apply_network_policy(demo_namespace)

        workload_app = None
        if workload_enabled:
            runtime_secret_name = str(res.get("workload_runtime_secret_name", "")).strip()
            if runtime_secret_name:
                runtime_data = self._resolve_workload_runtime_secret(
                    res.get("workload_runtime_secret_sources", {}),
                    {**res, "namespace": demo_namespace},
                )
                self._apply_workload_runtime_secret(
                    build_runtime_secret(
                        name=runtime_secret_name,
                        namespace=demo_namespace,
                        workshop_id=str(res.get("workshop_id", plan.request_id)),
                        seat_id=str(res.get("seat_id", plan.request_id)),
                        session_id=str(res.get("session_id", plan.request_id)),
                        tenant_id=tenant_id,
                        cluster_id=plan.target_cluster or "oberon",
                        string_data=runtime_data,
                    )
                )
            workload_app = build_workload_application(
                WorkloadSeat(
                    namespace=demo_namespace,
                    workshop_id=str(res.get("workshop_id", plan.request_id)),
                    seat_id=str(res.get("seat_id", plan.request_id)),
                    session_id=str(res.get("session_id", plan.request_id)),
                    tenant_id=tenant_id,
                    cluster_id=plan.target_cluster or "oberon",
                    destination_server=(
                        self._target.api_url if self._target else "https://kubernetes.default.svc"
                    ),
                    repo_url=str(res.get("workload_repo", "")),
                    revision=str(res.get("workload_revision", "")),
                    deploy_path=str(res.get("workload_deploy_path", "")),
                    release_name=str(res.get("workload_release_name", "workload")),
                    helm_values=dict(res.get("workload_helm_values", {})),
                    runtime_secret_name=runtime_secret_name,
                    runtime_secret_value_path=str(
                        res.get("workload_runtime_secret_value_path", "")
                    ),
                    identity_value_path=str(res.get("workload_identity_value_path", "")),
                    ignore_differences=tuple(
                        res.get("workload_ignore_differences", [])
                    ),
                ),
                argocd_namespace=os.environ.get("SHOWROOM_ARGOCD_NAMESPACE", "argocd"),
                argocd_project=os.environ.get("SHOWROOM_ARGOCD_PROJECT", "default"),
            )
            self._workload_gitops.apply(workload_app)

        # --- Step 3: Deploy filtered frontend in demo namespace ---
        gateway_url = ""
        if not operator_workshop:
            gateway_url = f"http://gateway.{gw_namespace}.svc.cluster.local:8080"
            self._deploy_demo_frontend(demo_namespace, demo_pages, gateway_url, catalog_item_id)
            time.sleep(5)

        # --- Step 4: Retrieve routes from demo namespace ---
        routes = self._get_routes(demo_namespace)
        apps_domain = (
            self._target.ingress_domain
            if self._target
            else os.environ.get("OPENSHIFT_APPS_DOMAIN", "apps.oberon.fm2aihpcsed.com")
        )
        workspace_route_name = str(res.get("workspace_route_name", "")).strip()
        workspace_url = (
            self._content_workspace_url(workspace_route_name, demo_namespace, apps_domain)
            if workspace_route_name
            else self._workspace_url(routes.get("demo", ""), res.get("workspace_path", ""))
        )

        workload_routes = dict(res.get("workload_routes", {}))
        if workload_enabled and workload_routes:
            routes = self._wait_for_named_routes(demo_namespace, set(workload_routes.values()))

        if showroom_enabled:
            console_url = (
                self._target.console_url.rstrip("/")
                if self._target and self._target.console_url
                else os.environ.get("OPENSHIFT_CONSOLE_URL", "").rstrip("/")
            )
            tool_tabs = self._resolve_showroom_tabs(
                res.get("showroom_tabs", []),
                namespace=demo_namespace,
                apps_domain=apps_domain,
                console_url=console_url,
                workload_routes=workload_routes,
                cluster_service_urls=(self._target.service_urls if self._target else {}),
                route_urls=routes,
            )
            showroom_app = build_showroom_application(
                ShowroomSeat(
                    namespace=demo_namespace,
                    workshop_id=str(res.get("workshop_id", plan.request_id)),
                    seat_id=str(res.get("seat_id", plan.request_id)),
                    session_id=str(res.get("session_id", plan.request_id)),
                    tenant_id=tenant_id,
                    participant_id=str(res.get("participant_id", "lab-user")),
                    workspace_url=workspace_url,
                    workspace_title=str(res.get("workspace_title", "RAG Workspace")),
                    content_repo_url=str(res["showroom_content_repo_url"]),
                    content_ref=str(res["showroom_content_ref"]),
                    apps_domain=apps_domain,
                    console_url=(
                        f"{console_url}/k8s/ns/{demo_namespace}/core~v1~Pod" if console_url else ""
                    ),
                    destination_server=self._target.api_url
                    if self._target
                    else "https://kubernetes.default.svc",
                    storage_class=self._target.storage_class if self._target else "nfs-storage",
                    cluster_id=self._target.cluster_id if self._target else "oberon",
                    cluster_display_name=(
                        self._target.display_name if self._target else "Oberon Primary"
                    ),
                    openshift_api_url=(self._target.api_url if self._target else ""),
                    maas_endpoint=maas_endpoint,
                    maas_api_key=session_maas_key,
                    maas_model=requested_models[0] if requested_models else "",
                    content_playbook=str(res.get("showroom_content_playbook", "site.yml")),
                    journey=str(res.get("showroom_journey", "guided-rag")),
                    content_only=bool(res.get("content_only", False)),
                    terminal_storage_enabled=bool(
                        res.get("showroom_terminal_storage", True)
                    ),
                    terminal_image=str(
                        res.get("showroom_support_images", {}).get(
                            "showroom_terminal", SHOWROOM_TERMINAL_IMAGE
                        )
                    ),
                    git_cloner_image=str(
                        res.get("showroom_support_images", {}).get(
                            "showroom_git_cloner", SHOWROOM_GIT_CLONER_IMAGE
                        )
                    ),
                    tool_tabs=tool_tabs,
                ),
                argocd_namespace=os.environ.get("SHOWROOM_ARGOCD_NAMESPACE", "argocd"),
                argocd_project=os.environ.get("SHOWROOM_ARGOCD_PROJECT", "default"),
                chart_version=os.environ.get("SHOWROOM_CHART_VERSION", "2.2.*"),
            )
            self._showroom_gitops.apply(showroom_app)
            routes = self._wait_for_showroom_route(demo_namespace)

        if workload_enabled:
            self._wait_for_workload_readiness(
                demo_namespace,
                list(res.get("workload_readiness", [])),
            )

        route_names = list(routes.keys())
        fallback_url = f"https://{demo_namespace}.apps.cluster.local"
        lab_url = (
            routes.get("showroom")
            or routes.get("showroom-proxy")
            or routes.get("demo")
            or (routes.get(route_names[0]) if route_names else fallback_url)
        )

        if not operator_workshop:
            self._active_namespaces[demo_namespace] = gw_namespace

        return ProvisionResult(
            namespace=demo_namespace,
            lab_url=lab_url,
            dashboard_url=f"https://{gw_namespace}.apps.cluster.local",
            resources={
                "namespace": demo_namespace,
                "gateway_namespace": None if operator_workshop else gw_namespace,
                "demo_pages": demo_pages,
                "catalog_item_id": catalog_item_id,
                "routes": routes,
                "showroom_url": routes.get("showroom") or routes.get("showroom-proxy"),
                "showroom_application": showroom_app["metadata"]["name"]
                if showroom_enabled
                else None,
                "workload_application": (
                    workload_app["metadata"]["name"] if workload_app else None
                ),
                "workspace_url": workspace_url,
                "gateway_url": gateway_url,
                "cluster_id": plan.target_cluster,
                "workshop_node_name": res.get("workshop_node_name"),
            },
            cluster_ref=plan.target_cluster,
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

    def _deploy_demo_frontend(
        self, namespace: str, pages: str, gateway_url: str, demo_name: str
    ) -> None:
        gateway = gateway_url.removeprefix("http://").removeprefix("https://")
        gw_host, _, gw_port = gateway.partition(":")
        gw_port = gw_port or "8080"
        dns_resolver = "172.30.0.10"
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as resolv_conf:
                dns_resolver = next(
                    line.split()[1] for line in resolv_conf if line.startswith("nameserver ")
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
            "config.json": json.dumps(
                {
                    "pages": [pages] if isinstance(pages, str) else pages,
                    "gateway_url": gateway_url,
                    "demo_name": demo_name,
                }
            ),
            "nginx.conf": nginx_conf,
        }
        try:
            self._core_v1.create_namespaced_config_map(
                namespace,
                client.V1ConfigMap(
                    metadata=client.V1ObjectMeta(name="demo-config"),
                    data=config_data,
                ),
            )
        except ApiException as e:
            if e.status != 409:
                pass

        FRONTEND_IMAGE = "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/inference-frontend:latest"

        container = client.V1Container(
            name="frontend",
            image=FRONTEND_IMAGE,
            ports=[client.V1ContainerPort(container_port=8080)],
            volume_mounts=[
                client.V1VolumeMount(
                    name="config",
                    mount_path="/opt/app-root/src/config.json",
                    sub_path="config.json",
                ),
                client.V1VolumeMount(
                    name="config", mount_path="/etc/nginx/nginx.conf", sub_path="nginx.conf"
                ),
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
                            client.V1Volume(
                                name="config",
                                config_map=client.V1ConfigMapVolumeSource(name="demo-config"),
                            ),
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
            self._core_v1.create_namespaced_service(
                namespace,
                client.V1Service(
                    metadata=client.V1ObjectMeta(name="demo-frontend"),
                    spec=client.V1ServiceSpec(
                        selector={"app": "demo-frontend"},
                        ports=[client.V1ServicePort(name="http", port=8080, target_port=8080)],
                    ),
                ),
            )
        except ApiException as e:
            if e.status != 409:
                pass

        oc = shutil.which("oc") or shutil.which("kubectl")
        if oc:
            subprocess.run(
                [
                    oc,
                    "create",
                    "route",
                    "edge",
                    "demo",
                    "--service=demo-frontend",
                    "--port=8080",
                    "-n",
                    namespace,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

    @staticmethod
    def _workspace_url(base_url: str, workspace_path: str) -> str:
        if not base_url:
            return ""
        path = str(workspace_path or "").strip()
        if not path:
            return base_url
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _content_workspace_url(route_name: str, namespace: str, apps_domain: str) -> str:
        """Return the stable hostname OpenShift assigns to an unnamed Route."""
        route = re.sub(r"[^a-z0-9-]+", "-", route_name.lower()).strip("-")
        if not route or not namespace or not apps_domain:
            return ""
        return f"https://{route}-{namespace}.{apps_domain}"

    @staticmethod
    def _resolve_showroom_tabs(
        tab_specs: list[dict],
        *,
        namespace: str,
        apps_domain: str,
        console_url: str,
        workload_routes: dict[str, str],
        cluster_service_urls: dict[str, str],
        route_urls: dict[str, str] | None = None,
    ) -> tuple[ShowroomToolTab, ...]:
        """Resolve catalog tab sources without inventing missing endpoints."""
        if not tab_specs:
            return ()
        resolved: list[ShowroomToolTab] = []
        route_urls = route_urls or {}
        for spec in tab_specs:
            title = str(spec.get("title") or spec.get("name") or "").strip()
            source = str(spec.get("source", "")).strip()
            if source == "showroom.terminal":
                resolved.append(ShowroomToolTab(name=title, path="/terminal", port=443))
                continue
            if source == "cluster.console_url" and console_url:
                resolved.append(
                    ShowroomToolTab(
                        name=title,
                        url=(f"{console_url.rstrip('/')}/k8s/ns/{namespace}/core~v1~Pod"),
                    )
                )
                continue
            if source.startswith("cluster.") and source.endswith("_url"):
                service = source.removeprefix("cluster.").removesuffix("_url")
                if cluster_service_urls.get(service):
                    resolved.append(ShowroomToolTab(name=title, url=cluster_service_urls[service]))
                    continue
            if source.startswith("workload.route."):
                route_id = source.removeprefix("workload.route.")
                route_name = workload_routes.get(route_id, "")
                if route_name:
                    route_url = route_urls.get(route_name) or (
                        f"https://{route_name}-{namespace}.{apps_domain}"
                    )
                    resolved.append(ShowroomToolTab(name=title, url=route_url))
                    continue
            if source.startswith("https://"):
                resolved.append(ShowroomToolTab(name=title, url=source))
                continue
            raise ValueError(f"Cannot resolve Showroom tab '{title}' from source '{source}'")
        return tuple(resolved)

    @staticmethod
    def _resolve_workload_runtime_secret(
        source_map: dict[str, object], resources: dict
    ) -> dict[str, str]:
        """Resolve approved dynamic, generated, and composed runtime fields."""
        requested_models = list(resources.get("requested_models", []))
        model_endpoints = resources.get("model_endpoints", {})
        if not isinstance(model_endpoints, dict):
            model_endpoints = {}
        available = {
            "maas_api_key": str(resources.get("maas_api_key", "")),
            "maas_endpoint": str(resources.get("maas_endpoint", "")),
            "requested_model": requested_models[0] if requested_models else "",
            "namespace": str(resources.get("namespace", "")),
        }
        result: dict[str, str] = {}
        templates: dict[str, str] = {}
        sensitive_markers = ("PASSWORD", "TOKEN", "SECRET", "API_KEY", "PRIVATE_KEY")

        for raw_key, contract in source_map.items():
            key = str(raw_key)
            if isinstance(contract, str):
                source = contract
                if source not in available:
                    raise ValueError(f"Unsupported workload runtime Secret source '{source}'")
                if not available[source]:
                    raise ValueError(f"Workload runtime Secret source '{source}' is unavailable")
                result[key] = available[source]
                continue
            if not isinstance(contract, dict):
                raise ValueError(f"Runtime Secret field '{key}' must be a source mapping")

            declared = [name for name in ("source", "value", "template") if name in contract]
            if len(declared) != 1:
                raise ValueError(
                    f"Runtime Secret field '{key}' must declare exactly one of source, value, or template"
                )
            if "value" in contract:
                if any(marker in key.upper() for marker in sensitive_markers):
                    raise ValueError(
                        f"Sensitive runtime field '{key}' cannot contain a catalog literal"
                    )
                result[key] = str(contract["value"])
                continue
            if "template" in contract:
                templates[key] = str(contract["template"])
                continue

            source = str(contract["source"])
            if source == "generated_password":
                length = contract.get("length", 32)
                if not isinstance(length, int) or not 24 <= length <= 128:
                    raise ValueError(
                        f"Generated runtime field '{key}' length must be between 24 and 128"
                    )
                result[key] = secrets.token_urlsafe(length)
                continue
            if source == "model_endpoint":
                model_id = str(contract.get("model", "")).strip()
                if not model_id:
                    raise ValueError(
                        f"Runtime Secret field '{key}' using model_endpoint must declare model"
                    )
                endpoint = str(model_endpoints.get(model_id, "")).strip()
                if not endpoint:
                    raise ValueError(f"Workload runtime model endpoint '{model_id}' is unavailable")
                result[key] = endpoint
                continue
            if source not in available:
                raise ValueError(f"Unsupported workload runtime Secret source '{source}'")
            if not available[source]:
                raise ValueError(f"Workload runtime Secret source '{source}' is unavailable")
            result[key] = available[source]

        placeholder = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
        for key, template in templates.items():
            fields = placeholder.findall(template)
            if (
                not fields
                or placeholder.sub("", template).count("{")
                or "}" in placeholder.sub("", template)
            ):
                raise ValueError(f"Runtime Secret template for '{key}' is invalid")
            unknown = sorted(set(fields).difference(result))
            if unknown:
                raise ValueError(
                    f"Runtime Secret template for '{key}' references unknown field(s): "
                    f"{', '.join(unknown)}"
                )
            result[key] = placeholder.sub(lambda match: result[match.group(1)], template)
        if source_map and not result:
            raise ValueError("Workload runtime Secret contract resolved no values")
        return result

    def _apply_workload_runtime_secret(self, secret: dict) -> None:
        namespace = secret["metadata"]["namespace"]
        name = secret["metadata"]["name"]
        try:
            self._core_v1.create_namespaced_secret(namespace, body=secret)
        except ApiException as exc:
            if exc.status != 409:
                raise ValueError(
                    f"Failed to create workload runtime Secret '{name}': {exc.reason}"
                ) from exc
            existing = self._core_v1.read_namespaced_secret(name, namespace)
            metadata = (
                existing.get("metadata", {}) if isinstance(existing, dict) else existing.metadata
            )
            labels = (
                metadata.get("labels", {}) if isinstance(metadata, dict) else metadata.labels or {}
            )
            expected_labels = secret["metadata"]["labels"]
            if (
                labels.get("app.kubernetes.io/managed-by") != "launchpad"
                or labels.get("launchpad.redhat.com/workshop-id")
                != expected_labels.get("launchpad.redhat.com/workshop-id")
                or labels.get("launchpad.redhat.com/seat-id")
                != expected_labels.get("launchpad.redhat.com/seat-id")
            ):
                raise ValueError(
                    f"Workload runtime Secret '{name}' is owned by another seat"
                ) from exc
            expected_session = expected_labels.get("launchpad.redhat.com/session-id")
            if labels.get("launchpad.redhat.com/session-id") != expected_session:
                self._core_v1.patch_namespaced_secret(name, namespace, body=secret)
                logger.info(
                    "Refreshed runtime Secret %s/%s for a retried seat session",
                    namespace,
                    name,
                )
                return
            logger.info(
                "Preserving existing runtime Secret %s/%s during idempotent retry",
                namespace,
                name,
            )

    def _apply_model_ca_bundle(
        self,
        namespace: str,
        *,
        resources: dict,
        cluster_id: str,
    ) -> None:
        """Copy the control-plane trust bundle into one model-consuming seat."""
        source_namespace = os.environ.get(
            "MODEL_CA_BUNDLE_NAMESPACE", "partner-ai-launchpad"
        )
        source_name = os.environ.get(
            "MODEL_CA_BUNDLE_CONFIGMAP", "launchpad-cluster-ca-bundle"
        )
        try:
            source = self._control_core_v1.read_namespaced_config_map(
                source_name, source_namespace
            )
        except ApiException as exc:
            raise ValueError(
                f"Model CA bundle ConfigMap '{source_namespace}/{source_name}' is unavailable"
            ) from exc
        data = source.get("data", {}) if isinstance(source, dict) else source.data or {}
        bundle = str(data.get("ca-bundle.crt", "")).strip()
        if not bundle:
            raise ValueError(
                f"Model CA bundle ConfigMap '{source_namespace}/{source_name}' has no ca-bundle.crt"
            )

        labels = {
            "app.kubernetes.io/component": "model-trust",
            "app.kubernetes.io/managed-by": "launchpad",
            "launchpad.redhat.com/workshop-id": str(resources.get("workshop_id", "")),
            "launchpad.redhat.com/seat-id": str(resources.get("seat_id", "")),
            "launchpad.redhat.com/session-id": str(resources.get("session_id", "")),
            "launchpad.redhat.com/tenant": str(resources.get("tenant_id", "default")),
            "launchpad.redhat.com/cluster-id": cluster_id,
        }
        body = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name="launchpad-model-ca-bundle",
                namespace=namespace,
                labels=labels,
            ),
            data={"ca-bundle.crt": bundle + "\n"},
        )
        try:
            self._core_v1.create_namespaced_config_map(namespace, body=body)
        except ApiException as exc:
            if exc.status != 409:
                raise ValueError(
                    f"Failed to create model CA bundle in namespace '{namespace}': {exc.reason}"
                ) from exc
            existing = self._core_v1.read_namespaced_config_map(
                "launchpad-model-ca-bundle", namespace
            )
            metadata = (
                existing.get("metadata", {})
                if isinstance(existing, dict)
                else existing.metadata
            )
            existing_labels = (
                metadata.get("labels", {})
                if isinstance(metadata, dict)
                else metadata.labels or {}
            )
            if (
                existing_labels.get("app.kubernetes.io/managed-by") != "launchpad"
                or existing_labels.get("launchpad.redhat.com/workshop-id")
                != labels["launchpad.redhat.com/workshop-id"]
                or existing_labels.get("launchpad.redhat.com/seat-id")
                != labels["launchpad.redhat.com/seat-id"]
            ):
                raise ValueError(
                    "Model CA bundle ConfigMap is owned by another seat"
                ) from exc
            self._core_v1.patch_namespaced_config_map(
                "launchpad-model-ca-bundle", namespace, body=body
            )

    def _apply_showroom_runtime_secret(
        self,
        *,
        namespace: str,
        resources: dict,
        cluster_id: str,
    ) -> None:
        """Write Showroom's seat model contract without exposing it to Argo CD."""
        maas_endpoint = self._showroom_maas_endpoint(resources)
        requested_models = list(resources.get("requested_models", []))
        self._apply_workload_runtime_secret(
            build_runtime_secret(
                name=SHOWROOM_RUNTIME_SECRET_NAME,
                namespace=namespace,
                workshop_id=str(resources.get("workshop_id", "")),
                seat_id=str(resources.get("seat_id", "")),
                session_id=str(resources.get("session_id", "")),
                tenant_id=str(resources.get("tenant_id", "default")),
                cluster_id=cluster_id,
                string_data={
                    "MAAS_API_KEY": str(resources.get("maas_api_key", "")),
                    "MAAS_ENDPOINT": maas_endpoint,
                    "MAAS_API_URL": (f"{maas_endpoint.rstrip('/')}/v1" if maas_endpoint else ""),
                    "MAAS_MODEL": requested_models[0] if requested_models else "",
                },
            )
        )

    def _wait_for_named_routes(self, namespace: str, route_names: set[str]) -> dict[str, str]:
        timeout = int(os.environ.get("WORKLOAD_ROUTE_TIMEOUT", "600"))
        deadline = time.time() + timeout
        routes: dict[str, str] = {}
        while time.time() < deadline:
            routes = self._get_routes(namespace)
            if route_names.issubset(routes):
                return routes
            time.sleep(HEALTH_INTERVAL)
        missing = sorted(route_names.difference(routes))
        raise ValueError(
            f"Workload routes were not ready in namespace '{namespace}' "
            f"within {timeout}s: {', '.join(missing)}"
        )

    def _wait_for_workload_readiness(self, namespace: str, checks: list[dict]) -> None:
        """Wait for declarative workload custom-resource conditions.

        Routes and Running pods are not sufficient evidence for operators that
        reconcile additional resources asynchronously. Every declared check
        must reach its expected condition before provisioning can report
        success.
        """
        for check in checks:
            group = str(check.get("group", ""))
            version = str(check.get("version", ""))
            plural = str(check.get("plural", ""))
            name = str(check.get("name", ""))
            condition_type = str(check.get("condition_type", "Ready"))
            expected_status = str(check.get("expected_status", "True"))
            timeout = max(0, int(check.get("timeout_seconds", WAIT_TIMEOUT)))
            interval = max(0, int(check.get("poll_interval_seconds", HEALTH_INTERVAL)))
            deadline = time.time() + timeout
            last_status = "missing"

            while True:
                try:
                    resource = self._custom_objects.get_namespaced_custom_object(
                        group,
                        version,
                        namespace,
                        plural,
                        name,
                    )
                    conditions = (resource.get("status") or {}).get("conditions") or []
                    observed = next(
                        (
                            condition
                            for condition in conditions
                            if str(condition.get("type")) == condition_type
                        ),
                        None,
                    )
                    if observed is not None:
                        last_status = str(observed.get("status", ""))
                        if last_status.casefold() == expected_status.casefold():
                            break
                except ApiException as exc:
                    if exc.status not in {404, 503}:
                        raise ValueError(
                            f"Cannot read workload readiness for {name} in namespace "
                            f"'{namespace}': {exc.status} {exc.reason}"
                        ) from exc

                if time.time() >= deadline:
                    raise ValueError(
                        f"Workload {name} did not reach "
                        f"{condition_type}={expected_status} in namespace '{namespace}' "
                        f"within {timeout}s (last status: {last_status})"
                    )
                time.sleep(interval)

    def _wait_for_showroom_route(self, namespace: str) -> dict[str, str]:
        """Wait for Argo CD to sync far enough for the chart route to exist."""
        # Large concurrent workshops can queue dozens of Applications behind
        # one Argo controller. Five minutes proved too short for the final
        # wave even though every Application subsequently became healthy.
        timeout = int(os.environ.get("SHOWROOM_ROUTE_TIMEOUT", "600"))
        deadline = time.time() + timeout
        tls_verify: bool | str = (
            os.environ.get("REQUESTS_CA_BUNDLE")
            or os.environ.get("SSL_CERT_FILE")
            or True
        )
        routes: dict[str, str] = {}
        while time.time() < deadline:
            routes = self._get_routes(namespace)
            showroom_url = routes.get("showroom") or routes.get("showroom-proxy")
            if showroom_url:
                try:
                    response = requests.get(
                        showroom_url,
                        timeout=5,
                        verify=tls_verify,
                        allow_redirects=True,
                    )
                    if response.status_code == 200:
                        return routes
                except requests.RequestException:
                    pass
            time.sleep(HEALTH_INTERVAL)
        raise ValueError(
            f"Showroom endpoint was not ready in namespace '{namespace}' within {timeout}s"
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
            self._rbac_v1.create_namespaced_role_binding(
                namespace="partner-ai-launchpad", body=body
            )
        except ApiException as exc:
            if exc.status != 409:
                pass

    def _grant_participant_access(
        self,
        namespace: str,
        participant_id: str,
        grant_application_logs: bool = False,
    ) -> None:
        if not participant_id:
            return
        body = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(name="launchpad-participant", namespace=namespace),
            role_ref=client.V1RoleRef(
                api_group="rbac.authorization.k8s.io",
                kind="ClusterRole",
                name="edit",
            ),
            subjects=[
                client.RbacV1Subject(
                    api_group="rbac.authorization.k8s.io",
                    kind="User",
                    name=participant_id,
                )
            ],
        )
        try:
            self._rbac_v1.create_namespaced_role_binding(namespace=namespace, body=body)
        except ApiException as exc:
            if exc.status != 409:
                raise ValueError(
                    f"Failed to grant workshop access to {participant_id}: {exc.reason}"
                ) from exc

        if not grant_application_logs:
            return
        log_binding = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(
                name="launchpad-participant-application-logs",
                namespace=namespace,
            ),
            role_ref=client.V1RoleRef(
                api_group="rbac.authorization.k8s.io",
                kind="ClusterRole",
                name="cluster-logging-application-view",
            ),
            subjects=[
                client.RbacV1Subject(
                    api_group="rbac.authorization.k8s.io",
                    kind="User",
                    name=participant_id,
                )
            ],
        )
        try:
            self._rbac_v1.create_namespaced_role_binding(
                namespace=namespace,
                body=log_binding,
            )
        except ApiException as exc:
            if exc.status != 409:
                raise ValueError(
                    f"Failed to grant application log access to {participant_id}: {exc.reason}"
                ) from exc

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

    def _select_workshop_node_name(self, request: LabRequest, metadata: dict) -> str:
        """Shard a workshop by seat while rejecting unstable or saturated workers.

        OpenShift's project node selector applies to operator-generated pods as
        well as chart-owned pods, which keeps each AgentOps seat together while
        preventing every DSPA from concentrating on the same worker.
        """
        if not metadata.get("workshop_node_spread", False):
            return ""

        min_ready_seconds = max(
            0, int(metadata.get("workshop_node_min_ready_seconds", 900))
        )
        protected_pods = max(
            1,
            int(metadata.get("seat_pods", 1))
            + int(metadata.get("seat_transient_pods", 0))
            + int(metadata.get("workshop_node_headroom_pods", 0)),
        )
        required_labels = {
            str(key): str(value)
            for key, value in (
                metadata.get("workshop_node_required_labels", {}) or {}
            ).items()
        }
        active_by_node: dict[str, int] = {}
        for pod in self._core_v1.list_pod_for_all_namespaces().items:
            if getattr(getattr(pod, "status", None), "phase", "") in {
                "Succeeded",
                "Failed",
            }:
                continue
            node_name = getattr(getattr(pod, "spec", None), "node_name", None)
            if node_name:
                active_by_node[node_name] = active_by_node.get(node_name, 0) + 1

        eligible: list[str] = []
        for node in self._core_v1.list_node().items:
            name = str(getattr(getattr(node, "metadata", None), "name", ""))
            labels = getattr(getattr(node, "metadata", None), "labels", None) or {}
            spec = getattr(node, "spec", None)
            status = getattr(node, "status", None)
            if not name or getattr(spec, "unschedulable", False):
                continue
            if any(labels.get(key) != value for key, value in required_labels.items()):
                continue
            if any(
                getattr(taint, "effect", "") in {"NoSchedule", "NoExecute"}
                for taint in (getattr(spec, "taints", None) or [])
            ):
                continue

            conditions = {
                getattr(condition, "type", ""): condition
                for condition in (getattr(status, "conditions", None) or [])
            }
            ready = conditions.get("Ready")
            if ready is None or getattr(ready, "status", "") != "True":
                continue
            if any(
                getattr(conditions.get(kind), "status", "False") == "True"
                for kind in ("MemoryPressure", "DiskPressure", "PIDPressure")
            ):
                continue
            transition = getattr(ready, "last_transition_time", None)
            if (
                transition is not None
                and time.time() - transition.timestamp() < min_ready_seconds
            ):
                continue

            allocatable = getattr(status, "allocatable", None) or {}
            pod_limit = int(allocatable.get("pods", 0))
            if pod_limit - active_by_node.get(name, 0) < protected_pods:
                continue
            eligible.append(name)

        if not eligible:
            raise ValueError(
                "No stable schedulable worker has the protected pod capacity "
                "required for this workshop seat"
            )

        seat_number = max(1, int(request.metadata.get("seat_number", 1)))
        return sorted(eligible)[(seat_number - 1) % len(eligible)]

    def _create_namespace(
        self,
        namespace: str,
        extra_labels: dict = None,
        extra_annotations: dict = None,
    ) -> None:
        labels = {
            "app.kubernetes.io/part-of": "launchpad",
            "app.kubernetes.io/managed-by": "launchpad",
            "pod-security.kubernetes.io/enforce": "restricted",
            "pod-security.kubernetes.io/warn": "restricted",
        }
        if extra_labels:
            labels.update(extra_labels)
        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels=labels,
                annotations=extra_annotations or {},
            )
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
            capture_output=True,
            text=True,
            timeout=120,
        )

        result = subprocess.run(
            [helm, "install", release_name, chart_path, "-n", namespace, "--timeout", "120s"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise ValueError(
                f"Helm install failed for '{release_name}' in '{namespace}':\n{result.stderr[:300]}"
            )

    def _deploy_kustomize(self, kustomize_path: str, namespace: str) -> None:
        kubectl = shutil.which("kubectl") or shutil.which("oc")
        if kubectl is None:
            raise ValueError("Neither 'kubectl' nor 'oc' found on PATH")

        result = subprocess.run(
            [kubectl, "apply", "-k", kustomize_path, "-n", namespace],
            capture_output=True,
            text=True,
            timeout=120,
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
        skip_files = {
            "namespace.yaml",
            "kustomization.yaml",
            "secrets-template.yaml",
            "keycloak-realm.yaml",
            "oauth-proxy.yaml",
            "postgres-backup.yaml",
            "frontend-deployment.yaml",
        }
        yamls = sorted([f for f in deploy_dir.glob("*.yaml") if f.name not in skip_files])

        if not yamls:
            raise ValueError(f"No YAML files found in {overlay_path}")

        for yaml_file in yamls:
            content = yaml_file.read_text()
            cleaned = "\n".join(
                line for line in content.splitlines() if not line.strip().startswith("namespace:")
            )
            cleaned = self._inject_storage_class(
                cleaned,
                os.environ.get("DEMO_STORAGE_CLASS") or os.environ.get("SANDBOX_STORAGE_CLASS", ""),
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
