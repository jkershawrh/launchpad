from __future__ import annotations

import copy
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger("launchpad.openshift.workload_gitops")

ARGO_GROUP = "argoproj.io"
ARGO_VERSION = "v1alpha1"
ARGO_PLURAL = "applications"
IMMUTABLE_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")


def workload_application_name(namespace: str) -> str:
    """Return the deterministic Argo CD Application name for a seat workload."""
    base = re.sub(r"[^a-z0-9-]+", "-", f"workload-{namespace}".lower()).strip("-")
    if len(base) <= 63:
        return base
    digest = hashlib.sha256(base.encode()).hexdigest()[:8]
    return f"{base[:54].rstrip('-')}-{digest}"


def _sensitive_value_path(value: Any, path: str = "values") -> str | None:
    """Find secret material that must never be serialized into an Application."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            compact = normalized.replace("_", "")
            child_path = f"{path}.{key}"
            if normalized in {"secrets", "data", "string_data", "stringdata"}:
                return child_path
            if normalized.endswith(
                ("api_key", "password", "private_key", "client_secret", "token", "credential")
            ) or compact.endswith(("apikey", "privatekey", "clientsecret")):
                return child_path
            found = _sensitive_value_path(child, child_path)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _sensitive_value_path(child, f"{path}[{index}]")
            if found:
                return found
    elif isinstance(value, str) and value.startswith(("sk-", "Bearer ")):
        return path
    return None


@dataclass(frozen=True)
class WorkloadSeat:
    namespace: str
    workshop_id: str
    seat_id: str
    session_id: str
    tenant_id: str
    cluster_id: str
    destination_server: str
    repo_url: str
    revision: str
    deploy_path: str
    release_name: str
    source_kind: str = "chart"
    helm_values: dict[str, Any] = field(default_factory=dict)
    kustomize_images: tuple[str, ...] = ()
    runtime_secret_name: str = ""
    runtime_secret_value_path: str = ""
    identity_value_path: str = ""
    ignore_differences: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not IMMUTABLE_GIT_SHA.fullmatch(self.revision):
            raise ValueError("Workload revision must be an immutable 40-character Git SHA")
        if not (
            self.repo_url.startswith("https://github.com/")
            or self.repo_url.startswith("git@github.com:")
        ):
            raise ValueError("Workload repository must use GitHub HTTPS or SSH transport")
        if not self.deploy_path.strip() or ".." in self.deploy_path.split("/"):
            raise ValueError("Workload deploy path must be a safe repository-relative path")
        if not DNS_LABEL.fullmatch(self.release_name):
            raise ValueError("Workload release name must be a DNS label")
        if self.source_kind not in {"chart", "helm", "kustomize"}:
            raise ValueError("Workload source kind must be chart, helm, or kustomize")
        if self.source_kind == "kustomize" and (
            self.runtime_secret_name or self.identity_value_path
        ):
            raise ValueError(
                "Kustomize workloads cannot use Helm runtime Secret or identity value paths"
            )
        for image in self.kustomize_images:
            if "=" not in image or "@sha256:" not in image:
                raise ValueError(
                    "Kustomize image overrides must map a source name to an immutable digest"
                )
        if bool(self.runtime_secret_name) != bool(self.runtime_secret_value_path):
            raise ValueError("Runtime Secret name and Helm value path must be declared together")
        if self.runtime_secret_name and not DNS_LABEL.fullmatch(self.runtime_secret_name):
            raise ValueError("Runtime Secret name must be a DNS label")
        if self.runtime_secret_value_path:
            leaf = re.sub(
                r"[^a-z0-9]+",
                "",
                self.runtime_secret_value_path.rsplit(".", 1)[-1].lower(),
            )
            if leaf not in {"existingsecret", "existingsecretname", "secretname"}:
                raise ValueError(
                    "Runtime Secret Helm value path must be an existing-Secret reference"
                )
        if self.identity_value_path and any(
            not part or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", part)
            for part in self.identity_value_path.split(".")
        ):
            raise ValueError("Workload identity Helm value path is invalid")
        for rule in self.ignore_differences:
            if set(rule) - {"group", "kind", "name", "namespace", "jsonPointers"}:
                raise ValueError("Workload ignore-differences rule contains unsupported fields")
            if not rule.get("kind") or not rule.get("name"):
                raise ValueError("Workload ignore-differences rule must name one resource")
            pointers = rule.get("jsonPointers")
            if not isinstance(pointers, list) or not pointers or any(
                not isinstance(pointer, str) or not pointer.startswith("/")
                for pointer in pointers
            ):
                raise ValueError(
                    "Workload ignore-differences rule requires explicit JSON pointers"
                )


def _set_value_path(values: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if not all(parts):
        raise ValueError("Runtime Secret Helm value path is invalid")
    current = values
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise TypeError(f"Helm value path '{path}' collides with a scalar value")
        current = child
    current[parts[-1]] = value


def build_workload_application(
    seat: WorkloadSeat,
    *,
    argocd_namespace: str = "argocd",
    argocd_project: str = "default",
) -> dict[str, Any]:
    """Build a secret-free, cluster-aware Argo CD Application for one seat."""
    helm_values = copy.deepcopy(seat.helm_values)
    if seat.runtime_secret_name:
        _set_value_path(helm_values, seat.runtime_secret_value_path, seat.runtime_secret_name)
    if seat.identity_value_path:
        _set_value_path(
            helm_values,
            seat.identity_value_path,
            {
                "workshopId": seat.workshop_id,
                "seatId": seat.seat_id,
                "sessionId": seat.session_id,
                "tenantId": seat.tenant_id,
                "clusterId": seat.cluster_id,
            },
        )
    sensitive_path = _sensitive_value_path(helm_values)
    if sensitive_path:
        raise ValueError(
            f"Helm values contain sensitive material at {sensitive_path}; "
            "put it in the seat runtime Secret"
        )

    labels = {
        "app.kubernetes.io/component": "workload",
        "app.kubernetes.io/managed-by": "launchpad",
        "launchpad.redhat.com/workshop-id": seat.workshop_id,
        "launchpad.redhat.com/seat-id": seat.seat_id,
        "launchpad.redhat.com/session-id": seat.session_id,
        "launchpad.redhat.com/tenant": seat.tenant_id,
        "launchpad.redhat.com/cluster-id": seat.cluster_id,
    }
    source: dict[str, Any] = {
        "repoURL": seat.repo_url,
        "targetRevision": seat.revision,
        "path": seat.deploy_path,
    }
    if seat.source_kind == "kustomize":
        source["kustomize"] = {"images": list(seat.kustomize_images)}
    else:
        source["helm"] = {
            "releaseName": seat.release_name,
            "values": yaml.safe_dump(helm_values, sort_keys=False),
        }

    spec: dict[str, Any] = {
        "project": argocd_project,
        "source": source,
        "destination": {
            "server": seat.destination_server,
            "namespace": seat.namespace,
        },
        "syncPolicy": {
            "automated": {"prune": True, "selfHeal": True},
            "syncOptions": ["CreateNamespace=true"],
        },
    }
    if seat.ignore_differences:
        spec["ignoreDifferences"] = copy.deepcopy(list(seat.ignore_differences))
        spec["syncPolicy"]["syncOptions"].append("RespectIgnoreDifferences=true")

    return {
        "apiVersion": f"{ARGO_GROUP}/{ARGO_VERSION}",
        "kind": "Application",
        "metadata": {
            "name": workload_application_name(seat.namespace),
            "namespace": argocd_namespace,
            "labels": labels,
            "finalizers": ["resources-finalizer.argocd.argoproj.io"],
        },
        "spec": spec,
    }


def build_runtime_secret(
    *,
    name: str,
    namespace: str,
    workshop_id: str,
    seat_id: str,
    session_id: str,
    tenant_id: str,
    cluster_id: str,
    string_data: dict[str, str],
) -> dict[str, Any]:
    """Build the runtime Secret sent directly to the execution cluster."""
    if not DNS_LABEL.fullmatch(name):
        raise ValueError("Runtime Secret name must be a DNS label")
    if not string_data or any(not isinstance(value, str) for value in string_data.values()):
        raise ValueError("Runtime Secret string_data must contain string values")
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/component": "workload-runtime",
                "app.kubernetes.io/managed-by": "launchpad",
                "launchpad.redhat.com/workshop-id": workshop_id,
                "launchpad.redhat.com/seat-id": seat_id,
                "launchpad.redhat.com/session-id": session_id,
                "launchpad.redhat.com/tenant": tenant_id,
                "launchpad.redhat.com/cluster-id": cluster_id,
            },
        },
        "type": "Opaque",
        "stringData": dict(string_data),
    }


class WorkloadGitOpsAdapter:
    def __init__(self, custom_objects, namespace: str = "argocd") -> None:
        self.custom_objects = custom_objects
        self.namespace = namespace

    def apply(self, application: dict[str, Any]) -> None:
        name = application["metadata"]["name"]
        try:
            self.custom_objects.create_namespaced_custom_object(
                ARGO_GROUP, ARGO_VERSION, self.namespace, ARGO_PLURAL, application
            )
        except Exception as exc:
            if getattr(exc, "status", None) != 409:
                raise
            self.custom_objects.patch_namespaced_custom_object(
                ARGO_GROUP,
                ARGO_VERSION,
                self.namespace,
                ARGO_PLURAL,
                name,
                application,
            )

    def delete_for_namespace(self, namespace: str, timeout: int = 60) -> None:
        name = workload_application_name(namespace)
        try:
            self.custom_objects.delete_namespaced_custom_object(
                ARGO_GROUP, ARGO_VERSION, self.namespace, ARGO_PLURAL, name
            )
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                return
            raise

        deadline = time.time() + timeout
        application = None
        while time.time() < deadline:
            try:
                application = self.custom_objects.get_namespaced_custom_object(
                    ARGO_GROUP, ARGO_VERSION, self.namespace, ARGO_PLURAL, name
                )
            except Exception as exc:
                if getattr(exc, "status", None) == 404:
                    return
                raise
            time.sleep(1)

        if application is None:
            try:
                application = self.custom_objects.get_namespaced_custom_object(
                    ARGO_GROUP, ARGO_VERSION, self.namespace, ARGO_PLURAL, name
                )
            except Exception as exc:
                if getattr(exc, "status", None) == 404:
                    return
                raise
        metadata = application.get("metadata", {})
        labels = metadata.get("labels", {})
        destination = application.get("spec", {}).get("destination", {})
        if (
            labels.get("app.kubernetes.io/managed-by") == "launchpad"
            and labels.get("app.kubernetes.io/component") == "workload"
            and metadata.get("deletionTimestamp")
            and destination.get("namespace") == namespace
        ):
            self.custom_objects.patch_namespaced_custom_object(
                ARGO_GROUP,
                ARGO_VERSION,
                self.namespace,
                ARGO_PLURAL,
                name,
                {"metadata": {"finalizers": []}},
            )
            logger.warning("Recovered stale workload Argo finalizer for %s", name)
            return
        raise TimeoutError(
            f"Workload Argo CD Application '{name}' was not deleted within {timeout}s"
        )
