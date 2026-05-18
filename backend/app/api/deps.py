from __future__ import annotations

import os
from types import SimpleNamespace

from app.adapters.mock.branding import FileBrandingAdapter
from app.adapters.mock.catalog import MockCatalogAdapter
from app.domain.models import Tenant
from app.services.provisioning import ProvisioningService
from app.storage.database import get_database_url


class TenantStore:
    def __init__(self, db_store=None) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._db = db_store

    def create(self, tenant: Tenant) -> Tenant:
        self._tenants[tenant.tenant_id] = tenant
        if self._db:
            self._db.save(tenant)
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        t = self._tenants.get(tenant_id)
        if not t and self._db:
            t = self._db.get(tenant_id)
            if t:
                self._tenants[tenant_id] = t
        return t

    def list_all(self) -> list[Tenant]:
        if self._db:
            db_tenants = self._db.list_all()
            for t in db_tenants:
                self._tenants[t.tenant_id] = t
        return list(self._tenants.values())


def _create_db_stores():
    if not get_database_url():
        return None
    from app.storage.stores import (
        PostgresCatalogStore,
        PostgresPlanStore,
        PostgresRequestStore,
        PostgresSessionStore,
        PostgresShowbackStore,
        PostgresTenantStore,
    )
    return SimpleNamespace(
        tenants=PostgresTenantStore(),
        requests=PostgresRequestStore(),
        sessions=PostgresSessionStore(),
        plans=PostgresPlanStore(),
        showback=PostgresShowbackStore(),
        catalog=PostgresCatalogStore(),
    )


def create_provisioning_service() -> ProvisioningService:
    mode = os.environ.get("LAUNCHPAD_MODE", "mock")
    db_stores = _create_db_stores()
    if mode == "local":
        from app.adapters.local.cleanup import LocalCleanupAdapter
        from app.adapters.local.provisioning import LocalProvisioningAdapter
        from app.adapters.local.validation import LocalValidationAdapter
        return ProvisioningService(
            provisioner=LocalProvisioningAdapter(),
            validator=LocalValidationAdapter(),
            cleanup=LocalCleanupAdapter(),
            db_stores=db_stores,
        )
    return ProvisioningService(db_stores=db_stores)


db_stores = _create_db_stores()
tenant_store = TenantStore(db_store=db_stores.tenants if db_stores else None)
provisioning_service = create_provisioning_service()
catalog_adapter = MockCatalogAdapter()
branding_adapter = FileBrandingAdapter()
