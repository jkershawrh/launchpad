from __future__ import annotations

import uuid

from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep
from app.adapters.interfaces import ProvisionResult


class MockProvisioningAdapter:
    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        namespace = f"lab-{request.tenant_id}-{uuid.uuid4().hex[:8]}"
        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=namespace,
            steps=[
                ProvisioningStep(
                    name="create-namespace",
                    adapter="mock",
                    action="create_namespace",
                    params={"namespace": namespace},
                    order=1,
                ),
                ProvisioningStep(
                    name="apply-quota",
                    adapter="mock",
                    action="apply_quota",
                    params={"quota_profile": request.quota_profile or catalog_item.default_quota_profile},
                    order=2,
                ),
                ProvisioningStep(
                    name="apply-rbac",
                    adapter="mock",
                    action="apply_rbac",
                    params={"tenant_id": request.tenant_id},
                    order=3,
                ),
                ProvisioningStep(
                    name="deploy-app",
                    adapter="mock",
                    action="deploy",
                    params={"catalog_item_id": catalog_item.catalog_item_id},
                    order=4,
                ),
            ],
            adapters_required=["mock"],
            validation_steps=["smoke-test"],
            estimated_duration="30s",
            required_resources={
                "hardware_profile": request.hardware_profile or catalog_item.default_hardware_profile,
                "quota_profile": request.quota_profile or catalog_item.default_quota_profile,
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        namespace = plan.target_namespace or f"lab-mock-{uuid.uuid4().hex[:8]}"
        return ProvisionResult(
            namespace=namespace,
            lab_url=f"https://lab.example.com/{namespace}",
            dashboard_url=f"https://dashboard.example.com/{namespace}",
            resources={
                "namespace": namespace,
                "steps_executed": len(plan.steps),
            },
        )
