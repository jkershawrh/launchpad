from __future__ import annotations

import os

from app.adapters.mock.branding import FileBrandingAdapter
from app.adapters.mock.catalog import MockCatalogAdapter
from app.domain.models import Tenant
from app.services.provisioning import ProvisioningService


class TenantStore:
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}

    def create(self, tenant: Tenant) -> Tenant:
        self._tenants[tenant.tenant_id] = tenant
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def list_all(self) -> list[Tenant]:
        return list(self._tenants.values())


def create_provisioning_service() -> ProvisioningService:
    mode = os.environ.get("LAUNCHPAD_MODE", "mock")
    if mode == "local":
        from app.adapters.local.cleanup import LocalCleanupAdapter
        from app.adapters.local.provisioning import LocalProvisioningAdapter
        from app.adapters.local.validation import LocalValidationAdapter
        return ProvisioningService(
            provisioner=LocalProvisioningAdapter(),
            validator=LocalValidationAdapter(),
            cleanup=LocalCleanupAdapter(),
        )
    return ProvisioningService()


tenant_store = TenantStore()
provisioning_service = create_provisioning_service()
catalog_adapter = MockCatalogAdapter()
branding_adapter = FileBrandingAdapter()
