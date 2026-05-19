from __future__ import annotations

import time
from typing import Optional

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException

    HAS_KUBERNETES = True
except ImportError:  # pragma: no cover
    HAS_KUBERNETES = False


class OpenShiftCleanupAdapter:
    def __init__(self) -> None:
        self._active_namespaces: dict[str, str] = {}

        if not HAS_KUBERNETES:
            raise ValueError(
                "The 'kubernetes' Python package is required for OpenShiftCleanupAdapter. "
                "Install it with: pip install kubernetes"
            )

        try:
            config.load_incluster_config()
        except config.ConfigException:
            try:
                config.load_kube_config()
            except config.ConfigException as exc:
                raise ValueError(
                    f"Unable to load Kubernetes configuration "
                    f"(tried in-cluster and kubeconfig): {exc}"
                ) from exc

        self._core_v1 = client.CoreV1Api()

    def cleanup(self, namespace: Optional[str] = None) -> bool:
        if not namespace:
            return False

        try:
            self._core_v1.delete_namespace(name=namespace)
        except ApiException as exc:
            if exc.status == 404:
                self._active_namespaces.pop(namespace, None)
                return True
            raise ValueError(
                f"Failed to delete namespace '{namespace}': {exc.status} {exc.reason}"
            ) from exc

        self._wait_for_deletion(namespace, timeout=60)
        self._active_namespaces.pop(namespace, None)
        return True

    def _wait_for_deletion(self, namespace: str, timeout: int = 60) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ns = self._core_v1.read_namespace(namespace)
                if ns.status and ns.status.phase == "Terminating":
                    time.sleep(3)
                    continue
            except ApiException as exc:
                if exc.status == 404:
                    return
            time.sleep(3)
