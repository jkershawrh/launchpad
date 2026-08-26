from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from kubernetes import client, config

from app.domain.clusters import ClusterTarget
from app.services.cluster_registry import ClusterRegistry


@dataclass(frozen=True)
class KubernetesClients:
    api_client: client.ApiClient
    core: client.CoreV1Api
    apps: client.AppsV1Api
    custom: client.CustomObjectsApi
    rbac: client.RbacAuthorizationV1Api
    authorization: client.AuthorizationV1Api


class ClusterClientFactory:
    """Build isolated API clients without changing global kubeconfig state."""

    def __init__(self, registry: ClusterRegistry, control_core=None) -> None:
        self.registry = registry
        self._control_core = control_core
        self._cache: dict[str, KubernetesClients] = {}

    def clients(self, cluster_id: str) -> KubernetesClients:
        if cluster_id in self._cache:
            return self._cache[cluster_id]
        target = self.registry.get(cluster_id)
        api_client = self._local_client() if target.local else self._remote_client(target)
        clients = KubernetesClients(
            api_client=api_client,
            core=client.CoreV1Api(api_client),
            apps=client.AppsV1Api(api_client),
            custom=client.CustomObjectsApi(api_client),
            rbac=client.RbacAuthorizationV1Api(api_client),
            authorization=client.AuthorizationV1Api(api_client),
        )
        self._cache[cluster_id] = clients
        return clients

    @staticmethod
    def _local_client() -> client.ApiClient:
        configuration = client.Configuration()
        try:
            config.load_incluster_config(client_configuration=configuration)
        except config.ConfigException:
            config.load_kube_config(client_configuration=configuration)
        return client.ApiClient(configuration)

    def _remote_client(self, target: ClusterTarget) -> client.ApiClient:
        if not target.credential_secret:
            raise ValueError(f"Cluster '{target.cluster_id}' has no credential Secret reference")
        control = self._control_core or client.CoreV1Api(self._local_client())
        secret_namespace, _, secret_name = target.credential_secret.partition("/")
        if not secret_name:
            raise ValueError("credential_secret must use namespace/name format")
        secret = control.read_namespaced_secret(secret_name, secret_namespace)
        encoded = (secret.data or {}).get("kubeconfig")
        if not encoded:
            raise ValueError(f"Credential Secret for '{target.cluster_id}' has no kubeconfig key")
        kubeconfig = yaml.safe_load(base64.b64decode(encoded).decode())
        configuration = client.Configuration()
        config.load_kube_config_from_dict(kubeconfig, client_configuration=configuration)
        return client.ApiClient(configuration)

