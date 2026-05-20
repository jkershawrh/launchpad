from __future__ import annotations

import logging
import subprocess
from typing import Any, Dict, Optional

from app.adapters.interfaces import ProvisionResult
from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep

logger = logging.getLogger(__name__)


class RHDPProvisioningAdapter:
    """Provisions workloads on a Sandbox API-claimed namespace.

    For RHDP quickstarts (provisioner_mode=rhdp), the namespace and credentials
    come from the Sandbox API placement. This adapter deploys the demo workload
    into that namespace using the SA token from the placement.
    """

    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        steps = []

        agnosticv_config = catalog_item.metadata.get("agnosticv_tenant_config")
        if agnosticv_config:
            steps.append(ProvisioningStep(
                name="sandbox-api-provisioned",
                adapter="sandbox-api",
                action="noop",
                params={"agnosticv_config": agnosticv_config},
                order=1,
            ))
        else:
            deploy_method = catalog_item.metadata.get("deploy_method", "kustomize")
            deploy_path = catalog_item.metadata.get("deploy_path", "")
            demo_pages = catalog_item.metadata.get("demo_pages", "all")

            steps.append(ProvisioningStep(
                name="deploy-workload",
                adapter="rhdp",
                action=deploy_method,
                params={
                    "deploy_path": deploy_path,
                    "demo_pages": demo_pages,
                    "demo_name": catalog_item.display_name,
                },
                order=1,
            ))

        namespace = f"launchpad-{request.tenant_id}-{catalog_item.catalog_item_id[:20]}"

        return ProvisioningPlan(
            request_id=request.request_id,
            steps=steps,
            target_namespace=namespace,
            required_resources={},
            adapters_required=["sandbox-api", "rhdp"],
            validation_steps=["pod-ready", "route-accessible"],
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        sandbox_data = plan.required_resources.get("sandbox_data", {})
        namespace = sandbox_data.get("namespace", plan.target_namespace)
        ingress_domain = sandbox_data.get("ingress_domain", "")
        console_url = sandbox_data.get("console_url", "")
        sa_token = sandbox_data.get("sa_token", "")
        sandbox_name = sandbox_data.get("sandbox_name", "")

        is_agnosticv_managed = any(
            s.action == "noop" and s.adapter == "sandbox-api"
            for s in plan.steps
        )

        if is_agnosticv_managed:
            lab_url = console_url
            dashboard_url = console_url
        else:
            for step in sorted(plan.steps, key=lambda s: s.order):
                if step.adapter == "rhdp" and sa_token:
                    self._deploy_to_remote(step, namespace, sa_token, ingress_domain)

            lab_url = f"https://demo-{namespace}.{ingress_domain}" if ingress_domain else ""
            dashboard_url = console_url

        return ProvisionResult(
            namespace=namespace,
            lab_url=lab_url,
            dashboard_url=dashboard_url,
            resources={
                "sandbox_name": sandbox_name,
                "ingress_domain": ingress_domain,
                "provisioned_by": "rhdp",
            },
        )

    def _deploy_to_remote(
        self,
        step: ProvisioningStep,
        namespace: str,
        sa_token: str,
        ingress_domain: str,
    ) -> None:
        deploy_path = step.params.get("deploy_path", "")
        deploy_method = step.action

        if not deploy_path:
            logger.warning("No deploy_path for step %s, skipping", step.name)
            return

        api_url = self._infer_api_url(ingress_domain)

        if deploy_method == "kustomize":
            self._apply_kustomize(deploy_path, namespace, api_url, sa_token)
        elif deploy_method == "helm":
            self._deploy_helm(deploy_path, namespace, api_url, sa_token)
        else:
            self._apply_kustomize(deploy_path, namespace, api_url, sa_token)

    def _apply_kustomize(
        self, path: str, namespace: str, api_url: str, token: str
    ) -> None:
        cmd = [
            "oc", "--server", api_url, "--token", token,
            "--insecure-skip-tls-verify",
            "apply", "-k", path, "-n", namespace,
        ]
        logger.info("Applying kustomize: %s", " ".join(cmd[:6]))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("Kustomize apply failed: %s", result.stderr)
            raise RuntimeError(f"Kustomize apply failed: {result.stderr}")

    def _deploy_helm(
        self, path: str, namespace: str, api_url: str, token: str
    ) -> None:
        cmd = [
            "helm", "upgrade", "--install", "demo", path,
            "--namespace", namespace,
            "--kube-apiserver", api_url,
            "--kube-token", token,
            "--kube-insecure-skip-tls-verify",
            "--wait", "--timeout", "5m",
        ]
        logger.info("Deploying helm chart: %s", path)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=360)
        if result.returncode != 0:
            logger.error("Helm deploy failed: %s", result.stderr)
            raise RuntimeError(f"Helm deploy failed: {result.stderr}")

    @staticmethod
    def _infer_api_url(ingress_domain: str) -> str:
        if not ingress_domain:
            return ""
        base = ingress_domain.replace("apps.", "", 1)
        return f"https://api.{base}:6443"
