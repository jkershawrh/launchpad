from __future__ import annotations

import uuid

from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep
from app.adapters.interfaces import ProvisionResult


class DemoProvisioningAdapter:
    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        demo_source = catalog_item.metadata.get("demo_source")
        if not demo_source:
            raise ValueError(
                f"Catalog item {catalog_item.catalog_item_id} has no demo_source in metadata"
            )

        namespace = f"demo-{request.tenant_id}-{demo_source.replace('/', '-')}-{uuid.uuid4().hex[:8]}"
        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=namespace,
            steps=[
                ProvisioningStep(
                    name="create-namespace",
                    adapter="demo",
                    action="create_namespace",
                    params={"namespace": namespace},
                    order=1,
                ),
                ProvisioningStep(
                    name="apply-quota",
                    adapter="demo",
                    action="apply_quota",
                    params={"quota_profile": request.quota_profile or catalog_item.default_quota_profile},
                    order=2,
                ),
                ProvisioningStep(
                    name="apply-rbac",
                    adapter="demo",
                    action="apply_rbac",
                    params={"tenant_id": request.tenant_id},
                    order=3,
                ),
                ProvisioningStep(
                    name="deploy-demo",
                    adapter="demo",
                    action="deploy_demo",
                    params={
                        "catalog_item_id": catalog_item.catalog_item_id,
                        "demo_source": demo_source,
                    },
                    order=4,
                ),
                ProvisioningStep(
                    name="configure-gateway",
                    adapter="demo",
                    action="configure_gateway",
                    params={"demo_source": demo_source},
                    order=5,
                ),
            ],
            adapters_required=["demo"],
            validation_steps=["gateway-health", "demo-source-exists", "config-valid"],
            estimated_duration="45s",
            required_resources={
                "hardware_profile": request.hardware_profile or catalog_item.default_hardware_profile,
                "quota_profile": request.quota_profile or catalog_item.default_quota_profile,
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        namespace = plan.target_namespace or f"demo-mock-{uuid.uuid4().hex[:8]}"
        demo_source = None
        for step in plan.steps:
            if step.params.get("demo_source"):
                demo_source = step.params["demo_source"]
                break
        demo_name = demo_source or "unknown"

        return ProvisionResult(
            namespace=namespace,
            lab_url=f"https://lab.example.com/{namespace}/{demo_name}",
            dashboard_url=f"https://dashboard.example.com/{namespace}/{demo_name}",
            resources={
                "namespace": namespace,
                "demo_source": demo_name,
                "steps_executed": len(plan.steps),
            },
        )
