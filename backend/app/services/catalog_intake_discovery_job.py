from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.domain.catalog_intake_discovery import (
    CatalogIntakeDiscoveryRequest,
    CatalogIntakeSourceApproval,
)

IMMUTABLE_IMAGE = re.compile(r"^[^\s]+@sha256:[0-9a-f]{64}$")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def build_discovery_job_bundle(
    request: CatalogIntakeDiscoveryRequest,
    *,
    source_approval: CatalogIntakeSourceApproval,
    namespace: str,
    image: str,
    egress_proxy_url: str,
    now: datetime | None = None,
) -> list[dict]:
    """Build a credential-free Job and its default-deny network boundary."""

    if not DNS_LABEL.fullmatch(namespace):
        raise ValueError("namespace must be a DNS label")
    if not IMMUTABLE_IMAGE.fullmatch(image):
        raise ValueError("worker image must use an immutable digest")
    selected_digest = "sha256:" + image.rsplit("@sha256:", 1)[1]
    if selected_digest != request.worker_image_digest:
        raise ValueError("worker image does not match the approved worker digest")
    now = now or datetime.now(UTC)
    approved_at = source_approval.approved_at
    expires_at = source_approval.expires_at
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        source_approval.approval_id != request.source_approval_id
        or source_approval.repository_url != request.repository_url
        or source_approval.revision != request.revision
        or not (approved_at <= now < expires_at)
    ):
        raise ValueError("source approval does not authorize this repository revision")
    proxy = urlparse(egress_proxy_url)
    if (
        proxy.scheme != "http"
        or not proxy.hostname
        or "." in proxy.hostname
        or proxy.port != 8080
        or proxy.username
        or proxy.password
        or proxy.path not in {"", "/"}
        or proxy.query
        or proxy.fragment
    ):
        raise ValueError("egress proxy must be an in-cluster HTTP service on port 8080")

    name = f"catalog-intake-{request.attempt_id}"
    labels = {
        "app.kubernetes.io/name": "catalog-intake-worker",
        "app.kubernetes.io/component": "repository-discovery",
        "launchpad.redhat.com/intake-id": request.intake_id,
        "launchpad.redhat.com/attempt-id": request.attempt_id,
    }
    request_json = request.model_dump_json()
    approval_json = source_approval.model_dump_json()
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": 300,
            "ttlSecondsAfterFinished": 600,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "automountServiceAccountToken": False,
                    "restartPolicy": "Never",
                    "securityContext": {
                        "runAsNonRoot": True,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "discovery",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["python3.11", "-m", "app.catalog_intake_worker_main"],
                            "env": [
                                {"name": "CATALOG_INTAKE_REQUEST_JSON", "value": request_json},
                                {"name": "CATALOG_INTAKE_SOURCE_APPROVAL_JSON", "value": approval_json},
                                {"name": "CATALOG_INTAKE_WORKSPACE", "value": "/workspace"},
                                {"name": "HTTP_PROXY", "value": egress_proxy_url},
                                {"name": "HTTPS_PROXY", "value": egress_proxy_url},
                                {"name": "NO_PROXY", "value": ""},
                                {"name": "GIT_CONFIG_NOSYSTEM", "value": "1"},
                                {"name": "GIT_TERMINAL_PROMPT", "value": "0"},
                                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                                {"name": "TMPDIR", "value": "/workspace"},
                            ],
                            "resources": {
                                "requests": {
                                    "cpu": "100m",
                                    "memory": "256Mi",
                                    "ephemeral-storage": "256Mi",
                                },
                                "limits": {
                                    "cpu": "1",
                                    "memory": "1Gi",
                                    "ephemeral-storage": "1Gi",
                                },
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "privileged": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/workspace"}
                            ],
                        }
                    ],
                    "volumes": [
                        {"name": "workspace", "emptyDir": {"sizeLimit": "512Mi"}}
                    ],
                },
            },
        },
    }
    network_policy = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "podSelector": {
                "matchLabels": {"launchpad.redhat.com/attempt-id": request.attempt_id}
            },
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [],
            "egress": [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "openshift-dns"
                                }
                            }
                        }
                    ],
                    "ports": [
                        {"protocol": "UDP", "port": 53},
                        {"protocol": "TCP", "port": 53},
                        {"protocol": "UDP", "port": 5353},
                        {"protocol": "TCP", "port": 5353},
                    ],
                },
                {
                    "to": [
                        {
                            "podSelector": {
                                "matchLabels": {
                                    "app.kubernetes.io/name": proxy.hostname
                                }
                            }
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 8080}],
                },
            ],
        },
    }
    # Ensure the serialized request stays within the policy payload ceiling.
    if len(json.dumps(job, separators=(",", ":")).encode()) > 65536:
        raise ValueError("discovery job payload exceeds the policy limit")
    return [job, network_policy]
