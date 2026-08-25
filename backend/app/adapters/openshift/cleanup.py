from __future__ import annotations

import logging
import os
import time
from typing import Optional

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException

    HAS_KUBERNETES = True
except ImportError:  # pragma: no cover
    HAS_KUBERNETES = False

logger = logging.getLogger("launchpad.openshift.cleanup")


class CleanupTimeoutError(Exception):
    pass


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
        self._rbac_v1 = client.RbacAuthorizationV1Api()
        from app.adapters.openshift.showroom_gitops import ShowroomGitOpsAdapter
        self._showroom_gitops = ShowroomGitOpsAdapter(
            client.CustomObjectsApi(), os.environ.get("SHOWROOM_ARGOCD_NAMESPACE", "argocd")
        )

    def cleanup(self, namespace: Optional[str] = None, timeout: int = 0) -> bool:
        """Request namespace deletion and optionally wait for completion.

        API-triggered cleanup uses the non-blocking default so OpenShift router
        timeouts do not turn a successful deletion request into a 504 response.
        Administrative callers can pass a positive timeout to wait and detect
        namespaces stuck in Terminating.
        """
        if not namespace:
            return False

        # Argo owns the Showroom resources. Delete its Application first or it
        # will self-heal by recreating the lab namespace after reclamation.
        showroom_gitops = getattr(self, "_showroom_gitops", None)
        if showroom_gitops is not None:
            showroom_delete_timeout = max(
                1, int(os.environ.get("SHOWROOM_DELETE_TIMEOUT", "60"))
            )
            showroom_gitops.delete_for_namespace(
                namespace, timeout=showroom_delete_timeout
            )

        try:
            self._core_v1.delete_namespace(name=namespace)
        except ApiException as exc:
            if exc.status == 404:
                self._cleanup_role_binding(namespace)
                self._active_namespaces.pop(namespace, None)
                return True
            raise ValueError(
                f"Failed to delete namespace '{namespace}': {exc.status} {exc.reason}"
            ) from exc

        if timeout > 0:
            self._wait_for_deletion(namespace, timeout=timeout)
        self._cleanup_role_binding(namespace)
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
        raise CleanupTimeoutError(
            f"Namespace '{namespace}' stuck in Terminating after {timeout}s — manual intervention required"
        )

    def _cleanup_role_binding(self, namespace: str) -> None:
        binding_name = f"{namespace}-image-puller"
        try:
            self._rbac_v1.delete_namespaced_role_binding(
                name=binding_name,
                namespace=os.environ.get("OPERATOR_NAMESPACE", "partner-ai-launchpad"),
            )
            logger.info("Deleted orphaned RoleBinding: %s", binding_name)
        except ApiException as exc:
            if exc.status == 404:
                pass
            else:
                logger.warning("Failed to delete RoleBinding %s: %s", binding_name, exc.reason)
