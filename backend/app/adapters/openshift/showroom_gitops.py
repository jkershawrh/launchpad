from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass

import yaml

logger = logging.getLogger("launchpad.openshift.showroom_gitops")

ARGO_GROUP = "argoproj.io"
ARGO_VERSION = "v1alpha1"
ARGO_PLURAL = "applications"
SHOWROOM_CHART_REPOSITORY = "https://rhpds.github.io/showroom-deployer"
SHOWROOM_CHART = "showroom-single-pod"
SHOWROOM_CHART_VERSION = "2.2.*"
SHOWROOM_TERMINAL_IMAGE = (
    "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/"
    "launchpad-showroom-terminal@sha256:"
    "164aa93d20af95dc916aa695556a1cae2ec057385ee1b254157df9eead099d9b"
)
SHOWROOM_GIT_CLONER_IMAGE = (
    "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/"
    "launchpad-showroom-git-cloner@sha256:"
    "3ae8e259f03888ee90526fd7d76375c4a6340df31242ede6be423604c3fdc26d"
)
SHOWROOM_RUNTIME_SECRET_NAME = "launchpad-participant-runtime"


def application_name(namespace: str) -> str:
    """Return a stable DNS-safe Argo CD Application name for a lab namespace."""
    base = re.sub(r"[^a-z0-9-]+", "-", f"showroom-{namespace}".lower()).strip("-")
    if len(base) <= 63:
        return base
    digest = hashlib.sha256(base.encode()).hexdigest()[:8]
    return f"{base[:54].rstrip('-')}-{digest}"


@dataclass(frozen=True)
class ShowroomToolTab:
    name: str
    url: str = ""
    path: str = ""
    port: int | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Showroom tab name is required")
        if bool(self.url) == bool(self.path):
            raise ValueError("Showroom tab must declare exactly one of url or path")
        if self.port is not None and not self.path:
            raise ValueError("Showroom tab port is valid only with path")

    def as_config(self) -> dict:
        config = {"name": self.name}
        if self.url:
            config["url"] = self.url
        else:
            config["path"] = self.path
            if self.port is not None:
                config["port"] = self.port
        return config


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
    workspace_title: str = "RAG Workspace"
    destination_server: str = "https://kubernetes.default.svc"
    storage_class: str = "nfs-storage"
    cluster_id: str = "oberon"
    cluster_display_name: str = "OpenShift cluster"
    console_url: str = ""
    content_playbook: str = "site.yml"
    ui_config_path: str = "ui-config.yml"
    journey: str = "guided-rag"
    content_only: bool = False
    openshift_api_url: str = ""
    maas_endpoint: str = ""
    maas_api_key: str = ""
    maas_model: str = ""
    tool_tabs: tuple[ShowroomToolTab, ...] = ()
    session_id: str = ""
    tenant_id: str = ""
    terminal_storage_enabled: bool = True
    terminal_image: str = SHOWROOM_TERMINAL_IMAGE
    git_cloner_image: str = SHOWROOM_GIT_CLONER_IMAGE

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
        "launchpad.redhat.com/cluster-id": seat.cluster_id,
    }
    if seat.session_id:
        labels["launchpad.redhat.com/session-id"] = seat.session_id
    if seat.tenant_id:
        labels["launchpad.redhat.com/tenant"] = seat.tenant_id
    user_data = {
        "guid": seat.seat_id,
        "user": seat.participant_id,
        "workshop_id": seat.workshop_id,
        "seat_id": seat.seat_id,
        "session_id": seat.session_id,
        "tenant_id": seat.tenant_id,
        "namespace": seat.namespace,
        "project_name": seat.namespace,
        "workspace_url": seat.workspace_url,
        "openshift_api_url": seat.openshift_api_url,
        "openshift_console_url": seat.console_url,
        "openshift_cluster_ingress_domain": seat.apps_domain,
        "cluster_display_name": seat.cluster_display_name,
        "content_revision": seat.content_ref,
        "showroom_journey": seat.journey,
        "maas_endpoint": seat.maas_endpoint,
        "maas_url": seat.maas_endpoint,
        "maas_api_url": f"{seat.maas_endpoint.rstrip('/')}/v1" if seat.maas_endpoint else "",
        "maas_model": seat.maas_model,
    }
    # Antora content is Showroom's primary guide pane, so it must not also be
    # configured as a tool tab. Doing so duplicates (and through a public
    # reverse proxy can recursively embed) the Showroom shell.
    if seat.tool_tabs:
        tabs = [tab.as_config() for tab in seat.tool_tabs]
    else:
        tabs = [{"name": "Terminal", "path": "/terminal", "port": 443}]
        if seat.workspace_url:
            tabs.insert(1, {"name": seat.workspace_title, "url": seat.workspace_url})
        if seat.console_url:
            tabs.append({"name": "OpenShift Console", "url": seat.console_url})
    ui_config = {
        "type": "showroom",
        "default_width": 40,
        # Public labs are reverse-proxied beneath a participant gateway.  URL
        # state persistence is unsafe there because an outer Showroom URL can
        # be restored inside one of its own frames.
        "persist_url_state": False,
        "tabs": tabs,
    }
    values = {
        "guid": seat.seat_id,
        "user": seat.participant_id,
        "deployer": {"domain": seat.apps_domain},
        "terminal": {
            "setup": "true",
            "image": seat.terminal_image,
            "storage": {
                "setup": "true",
                "storageClass": seat.storage_class,
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
        "git_cloner": {"image": seat.git_cloner_image},
    }
    if not seat.terminal_storage_enabled:
        values["terminal"]["storage"] = {"setup": "false"}
    if seat.journey == "openshift-operators" or seat.content_only:
        # Operator workshops need an oc terminal, not a heavyweight development
        # workstation. Keep each seat ephemeral and small enough for cohorts.
        values["terminal"]["storage"] = {"setup": "false"}
        values["terminal"]["resources"] = {
            "requests": {"cpu": "100m", "memory": "256Mi"},
            "limits": {"cpu": "500m", "memory": "512Mi"},
        }
        # The chart otherwise enables its separate wetty container by default.
        # The supported /terminal service already supplies this seat's shell.
        values["wetty"] = {"setup": "false"}
    return {
        "apiVersion": f"{ARGO_GROUP}/{ARGO_VERSION}",
        "kind": "Application",
        "metadata": {
            "name": name,
            "namespace": argocd_namespace,
            "labels": labels,
        },
        "spec": {
            "project": argocd_project,
            "source": {
                "repoURL": SHOWROOM_CHART_REPOSITORY,
                "chart": SHOWROOM_CHART,
                "targetRevision": chart_version,
                "helm": {
                    "releaseName": "showroom",
                    "values": yaml.safe_dump(values, sort_keys=False),
                },
            },
            "destination": {"server": seat.destination_server, "namespace": seat.namespace},
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

    def delete_for_namespace(self, namespace: str, timeout: int = 60) -> None:
        name = application_name(namespace)
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

        # Argo can leave its resources finalizer attached indefinitely even
        # after accepting deletion. Recover only Applications that Launchpad
        # owns, are already deleting, and target this exact seat namespace.
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
        recoverable = (
            labels.get("app.kubernetes.io/managed-by") == "launchpad"
            and metadata.get("deletionTimestamp")
            and destination.get("namespace") == namespace
        )
        if recoverable:
            self.custom_objects.patch_namespaced_custom_object(
                ARGO_GROUP,
                ARGO_VERSION,
                self.namespace,
                ARGO_PLURAL,
                name,
                {"metadata": {"finalizers": []}},
            )
            logger.warning(
                "Recovered stale Argo finalizer for Launchpad Application %s",
                name,
            )
            return
        raise TimeoutError(f"Argo CD Application '{name}' was not deleted within {timeout}s")
