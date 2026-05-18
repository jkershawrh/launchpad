from __future__ import annotations

from app.domain.models import CatalogItem, LabRequest
from app.adapters.interfaces import AutomationBundle


class MockAutomationGenerator:
    def generate(self, request: LabRequest, catalog_item: CatalogItem) -> AutomationBundle:
        return AutomationBundle(
            artifacts={
                "namespace.yaml": f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: lab-{request.tenant_id}\n",
                "quota.yaml": f"apiVersion: v1\nkind: ResourceQuota\nmetadata:\n  name: lab-quota\n  namespace: lab-{request.tenant_id}\n",
                "README.md": f"# {catalog_item.display_name}\n\nLab for tenant {request.tenant_id}.\n",
            },
            validated=True,
            dry_run_passed=True,
        )
