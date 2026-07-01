from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Dict, List

logger = logging.getLogger("launchpad.openshift.sandbox")

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException
except ImportError:
    pass

from app.adapters.interfaces import ProvisionResult
from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep

SANDBOX_IMAGE = "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/launchpad-sandbox:latest"
OPERATOR_NAMESPACE = os.environ.get("OPERATOR_NAMESPACE", "partner-ai-launchpad")

RESOURCE_TIERS = {
    "light": {"cpu_request": "500m", "cpu_limit": "2", "memory_request": "1Gi", "memory_limit": "4Gi", "storage": "20Gi"},
    "medium": {"cpu_request": "1", "cpu_limit": "4", "memory_request": "2Gi", "memory_limit": "8Gi", "storage": "50Gi"},
    "heavy": {"cpu_request": "2", "cpu_limit": "8", "memory_request": "4Gi", "memory_limit": "16Gi", "storage": "100Gi"},
}

STORAGE_TO_TIER = {"20Gi": "light", "50Gi": "medium", "100Gi": "heavy", "200Gi": "heavy"}

# Max tier allowed per quota profile
QUOTA_MAX_TIER = {
    "small": "light",
    "standard": "medium",
    "large": "heavy",
}
TIER_ORDER = ["light", "medium", "heavy"]


class OpenShiftSandboxProvisioner:
    def __init__(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._core_v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()
        self._custom = client.CustomObjectsApi()
        self._rbac_v1 = client.RbacAuthorizationV1Api()

    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        meta = catalog_item.metadata or {}
        req_meta = request.metadata or {}
        sandbox_config = req_meta.get("sandbox_config", {})

        stack_level = sandbox_config.get("stack_level") or meta.get("stack_level", "minimal")
        access_methods = sandbox_config.get("access_methods") or meta.get("access_methods", ["ssh"])
        storage_size = sandbox_config.get("storage_size", "20Gi")
        requested_tier = STORAGE_TO_TIER.get(storage_size, "light")

        quota_profile = request.quota_profile or catalog_item.default_quota_profile or "standard"
        max_tier = QUOTA_MAX_TIER.get(quota_profile, "medium")
        if TIER_ORDER.index(requested_tier) > TIER_ORDER.index(max_tier):
            raise ValueError(
                f"Compute tier '{requested_tier}' exceeds quota profile '{quota_profile}' "
                f"(max allowed: '{max_tier}'). Request a smaller storage size or upgrade quota."
            )
        compute_tier = requested_tier

        namespace = f"launchpad-sandbox-{request.tenant_id}-{uuid.uuid4().hex[:8]}"

        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=namespace,
            steps=[
                ProvisioningStep(name="create-namespace", adapter="openshift-sandbox", action="create_namespace", order=1),
                ProvisioningStep(name="grant-image-pull", adapter="openshift-sandbox", action="grant_image_pull", order=2),
                ProvisioningStep(name="create-secrets", adapter="openshift-sandbox", action="create_secrets", order=3),
                ProvisioningStep(name="create-pvc", adapter="openshift-sandbox", action="create_pvc", order=4),
                ProvisioningStep(name="create-deployment", adapter="openshift-sandbox", action="create_deployment", order=5),
                ProvisioningStep(name="create-service", adapter="openshift-sandbox", action="create_service", order=6),
                ProvisioningStep(name="create-routes", adapter="openshift-sandbox", action="create_routes", order=7),
                ProvisioningStep(name="wait-for-ready", adapter="openshift-sandbox", action="wait_ready", order=8),
            ],
            adapters_required=["openshift-sandbox"],
            validation_steps=["pod-ready", "ssh-reachable"],
            estimated_duration="60s",
            required_resources={
                "sandbox_type": meta.get("sandbox_type", "custom"),
                "stack_level": stack_level,
                "access_methods": access_methods,
                "compute_tier": compute_tier,
                "storage_size": storage_size,
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        namespace = plan.target_namespace
        res = plan.required_resources
        stack_level = res.get("stack_level", "minimal")
        access_methods = res.get("access_methods", ["ssh"])
        compute_tier = res.get("compute_tier", "light")
        storage_size = res.get("storage_size", "20Gi")
        tier = RESOURCE_TIERS.get(compute_tier, RESOURCE_TIERS["light"])

        # 1. Create namespace with tracking labels
        ns_labels = {
            "launchpad.redhat.com/tenant": plan.required_resources.get("tenant_id", ""),
            "launchpad.redhat.com/session-id": plan.request_id[:8],
            "launchpad.redhat.com/catalog-item": plan.required_resources.get("catalog_item_id", ""),
            "launchpad.redhat.com/purpose": plan.required_resources.get("purpose", "self-service"),
        }
        workshop_id = plan.required_resources.get("workshop_id")
        if workshop_id:
            ns_labels["launchpad.redhat.com/workshop-id"] = workshop_id
        self._create_namespace(namespace, extra_labels=ns_labels)

        # 2. Grant image pull
        self._grant_image_pull(namespace)

        # 3. Create secrets (use session-specific MaaS key for tracking)
        ssh_password = f"lab-{uuid.uuid4().hex[:8]}"
        session_maas_key = res.get("maas_api_key", os.environ.get("LITELLM_API_KEY", ""))
        self._create_secrets(namespace, ssh_password, session_maas_key)

        # 4. Create PVC
        self._create_pvc(namespace, storage_size)

        # 5. Create Deployment
        self._create_deployment(namespace, stack_level, tier)

        # 6. Create Service
        self._create_service(namespace, access_methods)

        # 7. Create Routes
        routes = self._create_routes(namespace, access_methods)

        # 8. Wait for pod ready
        time.sleep(5)

        connection_info = {
            "ssh_password": ssh_password,
            "stack_level": stack_level,
            "compute_tier": compute_tier,
        }
        lab_url = ""

        for name, host in routes.items():
            url = f"https://{host}"
            connection_info[name] = url
            if "jupyter" in name:
                lab_url = url
            elif not lab_url:
                lab_url = url

        if "ssh" in [m for m in access_methods]:
            ssh_route = routes.get("sandbox-ssh", "")
            if ssh_route:
                connection_info["ssh"] = f"ssh lab-user@{ssh_route} -p 2222"

        aap_url = os.environ.get("AAP_URL")
        if aap_url:
            connection_info["aap_url"] = aap_url

        return ProvisionResult(
            namespace=namespace,
            lab_url=lab_url or f"https://{namespace}.apps.cluster.local",
            dashboard_url=lab_url,
            resources={
                "namespace": namespace,
                "sandbox_type": res.get("sandbox_type", "custom"),
                "stack_level": stack_level,
                "access_methods": access_methods,
                "compute_tier": compute_tier,
                "connection_info": connection_info,
                "container_name": f"sandbox-{namespace}",
            },
        )

    def _create_namespace(self, namespace: str, extra_labels: dict = None) -> None:
        labels = {
            "app": "launchpad-sandbox",
            "app.kubernetes.io/part-of": "launchpad",
            "app.kubernetes.io/managed-by": "launchpad",
            "pod-security.kubernetes.io/enforce": "restricted",
            "pod-security.kubernetes.io/warn": "restricted",
        }
        if extra_labels:
            labels.update(extra_labels)
        try:
            self._core_v1.create_namespace(client.V1Namespace(
                metadata=client.V1ObjectMeta(name=namespace, labels=labels)
            ))
        except ApiException as e:
            if e.status != 409:
                raise ValueError(f"Failed to create namespace: {e.reason}")

    def _grant_image_pull(self, namespace: str) -> None:
        try:
            self._rbac_v1.create_namespaced_role_binding(
                namespace=OPERATOR_NAMESPACE,
                body=client.V1RoleBinding(
                    metadata=client.V1ObjectMeta(name=f"{namespace}-image-puller", namespace=OPERATOR_NAMESPACE),
                    role_ref=client.V1RoleRef(api_group="rbac.authorization.k8s.io", kind="ClusterRole", name="system:image-puller"),
                    subjects=[client.RbacV1Subject(kind="Group", name=f"system:serviceaccounts:{namespace}", api_group="rbac.authorization.k8s.io")],
                ),
            )
        except ApiException as e:
            if e.status != 409:
                logger.warning("Failed to create image-pull RoleBinding for %s: %s", namespace, e.reason)

    def _create_secrets(self, namespace: str, ssh_password: str, maas_key: str = "") -> None:
        litellm_key = maas_key or os.environ.get("LITELLM_API_KEY", "")
        for name, data in [
            ("sandbox-credentials", {"SSH_USER": "lab-user", "SSH_PASSWORD": ssh_password}),
            ("maas-config", {
                "MODEL_ENDPOINT": os.environ.get("LITELLM_API_BASE", ""),
                "LITELLM_API_KEY": litellm_key,
                "LITELLM_API_BASE": os.environ.get("LITELLM_API_BASE", ""),
                "MAAS_SESSION_KEY": maas_key,
                "MAAS_RATE_LIMIT_RPM": os.environ.get("MAAS_RATE_LIMIT_RPM", "60"),
            }),
        ]:
            try:
                self._core_v1.create_namespaced_secret(namespace, client.V1Secret(
                    metadata=client.V1ObjectMeta(name=name),
                    string_data=data,
                ))
            except ApiException as e:
                if e.status != 409:
                    logger.warning("Failed to create secret '%s' in namespace %s: %s", name, namespace, e.reason)

    def _create_pvc(self, namespace: str, storage_size: str) -> None:
        try:
            self._core_v1.create_namespaced_persistent_volume_claim(namespace, client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(name="sandbox-home"),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],
                    resources=client.V1VolumeResourceRequirements(requests={"storage": storage_size}),
                ),
            ))
        except ApiException as e:
            if e.status != 409:
                logger.warning("Failed to create PVC in namespace %s: %s", namespace, e.reason)

    def _create_deployment(self, namespace: str, stack_level: str, tier: Dict) -> None:
        container = client.V1Container(
            name="sandbox",
            image=SANDBOX_IMAGE,
            ports=[
                client.V1ContainerPort(container_port=2222, name="ssh"),
                client.V1ContainerPort(container_port=8888, name="jupyter"),
                client.V1ContainerPort(container_port=8443, name="vscode"),
            ],
            env=[
                client.V1EnvVar(name="STACK_LEVEL", value=stack_level),
            ],
            env_from=[
                client.V1EnvFromSource(secret_ref=client.V1SecretEnvSource(name="maas-config", optional=True)),
            ],
            volume_mounts=[
                client.V1VolumeMount(name="home", mount_path="/home/lab-user/workspace"),
            ],
            resources=client.V1ResourceRequirements(
                requests={"cpu": tier["cpu_request"], "memory": tier["memory_request"]},
                limits={"cpu": tier["cpu_limit"], "memory": tier["memory_limit"]},
            ),
        )

        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(name="sandbox", labels={"app": "sandbox"}),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": "sandbox"}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "sandbox"}),
                    spec=client.V1PodSpec(
                        containers=[container],
                        volumes=[
                            client.V1Volume(name="home", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name="sandbox-home")),
                        ],
                    ),
                ),
            ),
        )

        try:
            self._apps_v1.create_namespaced_deployment(namespace, deployment)
        except ApiException as e:
            if e.status != 409:
                raise ValueError(f"Failed to create sandbox deployment: {e.reason}")

    def _create_service(self, namespace: str, access_methods: List[str]) -> None:
        ports = [client.V1ServicePort(name="ssh", port=2222, target_port=2222)]
        if "jupyter" in access_methods:
            ports.append(client.V1ServicePort(name="jupyter", port=8888, target_port=8888))
        if "vscode" in access_methods:
            ports.append(client.V1ServicePort(name="vscode", port=8443, target_port=8443))

        try:
            self._core_v1.create_namespaced_service(namespace, client.V1Service(
                metadata=client.V1ObjectMeta(name="sandbox"),
                spec=client.V1ServiceSpec(
                    selector={"app": "sandbox"},
                    ports=ports,
                    type="ClusterIP",
                ),
            ))
        except ApiException as e:
            if e.status != 409:
                logger.warning("Failed to create service in namespace %s: %s", namespace, e.reason)

    def _create_routes(self, namespace: str, access_methods: List[str]) -> Dict[str, str]:
        routes = {}
        route_defs = []

        if "ssh" in access_methods:
            route_defs.append({
                "name": "sandbox-ssh",
                "port": "ssh",
                "tls_termination": "passthrough",
            })

        if "jupyter" in access_methods:
            route_defs.append({
                "name": "sandbox-jupyter",
                "port": "jupyter",
                "tls_termination": "edge",
            })

        if "vscode" in access_methods:
            route_defs.append({
                "name": "sandbox-vscode",
                "port": "vscode",
                "tls_termination": "edge",
            })

        for rd in route_defs:
            route_body = {
                "apiVersion": "route.openshift.io/v1",
                "kind": "Route",
                "metadata": {"name": rd["name"], "namespace": namespace},
                "spec": {
                    "to": {"kind": "Service", "name": "sandbox"},
                    "port": {"targetPort": rd["port"]},
                    "tls": {
                        "termination": rd["tls_termination"],
                        "insecureEdgeTerminationPolicy": "Redirect",
                    },
                },
            }

            try:
                result = self._custom.create_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=namespace,
                    plural="routes",
                    body=route_body,
                )
                host = result.get("spec", {}).get("host", result.get("status", {}).get("ingress", [{}])[0].get("host", ""))
                if not host:
                    ingress_domain = os.environ.get("OPENSHIFT_INGRESS_DOMAIN", "apps.cluster.example.com")
                    host = f"{rd['name']}-{namespace}.{ingress_domain}"
                routes[rd["name"]] = host
            except ApiException:
                ingress_domain = os.environ.get("OPENSHIFT_INGRESS_DOMAIN", "apps.cluster.example.com")
                routes[rd["name"]] = f"{rd['name']}-{namespace}.{ingress_domain}"

        return routes
