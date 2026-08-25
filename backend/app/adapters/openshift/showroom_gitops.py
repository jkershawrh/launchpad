from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import yaml

ARGO_GROUP = "argoproj.io"
ARGO_VERSION = "v1alpha1"
ARGO_PLURAL = "applications"
SHOWROOM_CHART_REPOSITORY = "https://rhpds.github.io/showroom-deployer"
SHOWROOM_CHART = "showroom-single-pod"
SHOWROOM_CHART_VERSION = "2.2.*"


def application_name(namespace: str) -> str:
    """Return a stable DNS-safe Argo CD Application name for a lab namespace."""
    base = re.sub(r"[^a-z0-9-]+", "-", f"showroom-{namespace}".lower()).strip("-")
    if len(base) <= 63:
        return base
    digest = hashlib.sha256(base.encode()).hexdigest()[:8]
    return f"{base[:54].rstrip('-')}-{digest}"


@dataclass(frozen=True)
class ShowroomSeat:
    namespace: str
    workshop_id: str
    seat_id: str
    participant_id: str
    workspace_url: str
    content_repo_url: str
    content_ref: str
    apps_domain: str
    console_url: str = ""
    content_playbook: str = "site.yml"
    ui_config_path: str = "ui-config.yml"

    def __post_init__(self) -> None:
        if not self.content_ref.strip():
            raise ValueError("Showroom content_ref must be a Git commit or tag")


def build_showroom_application(
    seat: ShowroomSeat,
    *,
    argocd_namespace: str = "argocd",
    argocd_project: str = "default",
    chart_version: str = SHOWROOM_CHART_VERSION,
) -> dict:
    name = application_name(seat.namespace)
    labels = {
        "app.kubernetes.io/component": "showroom",
        "app.kubernetes.io/managed-by": "launchpad",
        "launchpad.redhat.com/workshop-id": seat.workshop_id,
        "launchpad.redhat.com/seat-id": seat.seat_id,
    }
    user_data = {
        "user": seat.participant_id,
        "workshop_id": seat.workshop_id,
        "seat_id": seat.seat_id,
        "namespace": seat.namespace,
        "workspace_url": seat.workspace_url,
        "openshift_console_url": seat.console_url,
        "content_revision": seat.content_ref,
        "showroom_journey": "guided-rag",
    }
    tabs = [
        {"name": "Instructions", "path": "/instructions", "port": 443},
        {"name": "Terminal", "path": "/terminal", "port": 443},
    ]
    if seat.workspace_url:
        tabs.insert(1, {"name": "RAG Workspace", "url": seat.workspace_url})
    if seat.console_url:
        tabs.append({"name": "OpenShift Console", "url": seat.console_url})
    ui_config = {
        "type": "showroom",
        "default_width": 40,
        "persist_url_state": True,
        "tabs": tabs,
    }
    values = {
        "guid": seat.seat_id,
        "user": seat.participant_id,
        "deployer": {"domain": seat.apps_domain},
        "terminal": {
            "setup": "true",
            "image": "quay.io/rhpds/openshift-showroom-terminal-ocp:4.20",
            "storage": {
                "setup": "true",
                "storageClass": "nfs-storage",
                "pvcSize": "5Gi",
            },
        },
        "content": {
            "repoUrl": seat.content_repo_url,
            "repoRef": seat.content_ref,
            "antoraPlaybook": seat.content_playbook,
            "uiConfig": yaml.safe_dump(ui_config, sort_keys=False),
            "user_data": yaml.safe_dump(user_data, sort_keys=False),
            "zero_touch_bundle": "https://github.com/rhpds/nookbag/releases/download/nookbag-v0.4.0/nookbag-v0.4.0.zip",
        },
    }
    return {
        "apiVersion": f"{ARGO_GROUP}/{ARGO_VERSION}",
        "kind": "Application",
        "metadata": {
            "name": name,
            "namespace": argocd_namespace,
            "labels": labels,
            "finalizers": ["resources-finalizer.argocd.argoproj.io"],
        },
        "spec": {
            "project": argocd_project,
            "source": {
                "repoURL": SHOWROOM_CHART_REPOSITORY,
                "chart": SHOWROOM_CHART,
                "targetRevision": chart_version,
                "helm": {"releaseName": "showroom", "values": yaml.safe_dump(values, sort_keys=False)},
            },
            "destination": {"server": "https://kubernetes.default.svc", "namespace": seat.namespace},
            "syncPolicy": {
                "automated": {"prune": True, "selfHeal": True},
                "syncOptions": ["CreateNamespace=true"],
            },
        },
    }


class ShowroomGitOpsAdapter:
    def __init__(self, custom_objects, namespace: str = "argocd") -> None:
        self.custom_objects = custom_objects
        self.namespace = namespace

    def apply(self, application: dict) -> None:
        name = application["metadata"]["name"]
        try:
            self.custom_objects.create_namespaced_custom_object(
                ARGO_GROUP, ARGO_VERSION, self.namespace, ARGO_PLURAL, application
            )
        except Exception as exc:
            if getattr(exc, "status", None) != 409:
                raise
            self.custom_objects.patch_namespaced_custom_object(
                ARGO_GROUP, ARGO_VERSION, self.namespace, ARGO_PLURAL, name, application
            )

    def delete_for_namespace(self, namespace: str) -> None:
        try:
            self.custom_objects.delete_namespaced_custom_object(
                ARGO_GROUP, ARGO_VERSION, self.namespace, ARGO_PLURAL, application_name(namespace)
            )
        except Exception as exc:
            if getattr(exc, "status", None) != 404:
                raise
