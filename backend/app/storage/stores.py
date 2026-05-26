"""
Data-access layer using asyncpg.

Each store class provides sync wrappers that internally run async operations.
When the pool is unavailable (no DATABASE_URL), all operations are no-ops that
return None or empty lists, allowing in-memory fallback at the service layer.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

from app.domain.models import (
    CatalogItem,
    LabRequest,
    LabSession,
    ProvisioningPlan,
    ShowbackRecord,
    Tenant,
)
from app.storage.database import get_pool

logger = logging.getLogger("launchpad.stores")


def _run(coro):
    """Run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # We're inside an already-running event loop (e.g. during tests
        # or within an async framework). Create a new loop in a thread.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    return asyncio.run(coro)


class PostgresTenantStore:
    def save(self, tenant: Tenant) -> None:
        pool = get_pool()
        if not pool:
            return
        _run(self._save(pool, tenant))

    async def _save(self, pool, tenant: Tenant) -> None:
        data = json.dumps(tenant.model_dump(mode="json"))
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO tenants (tenant_id, data)
                   VALUES ($1, $2::jsonb)
                   ON CONFLICT (tenant_id) DO UPDATE SET data = $2::jsonb""",
                tenant.tenant_id, data,
            )

    def get(self, tenant_id: str) -> Optional[Tenant]:
        pool = get_pool()
        if not pool:
            return None
        return _run(self._get(pool, tenant_id))

    async def _get(self, pool, tenant_id: str) -> Optional[Tenant]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM tenants WHERE tenant_id = $1", tenant_id
            )
            if row:
                return Tenant.model_validate(json.loads(row["data"]))
        return None

    def list_all(self) -> List[Tenant]:
        pool = get_pool()
        if not pool:
            return []
        return _run(self._list_all(pool))

    async def _list_all(self, pool) -> List[Tenant]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT data FROM tenants")
            return [Tenant.model_validate(json.loads(r["data"])) for r in rows]


class PostgresSessionStore:
    def save(self, session: LabSession) -> None:
        pool = get_pool()
        if not pool:
            return
        _run(self._save(pool, session))

    async def _save(self, pool, session: LabSession) -> None:
        data = json.dumps(session.model_dump(mode="json"))
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT session_id FROM lab_sessions WHERE session_id = $1",
                session.session_id,
            )
            if existing:
                await conn.execute(
                    """UPDATE lab_sessions
                       SET status = $1, namespace = $2, data = $3::jsonb, updated_at = NOW()
                       WHERE session_id = $4""",
                    session.status.value, session.namespace, data, session.session_id,
                )
            else:
                await conn.execute(
                    """INSERT INTO lab_sessions
                       (session_id, request_id, tenant_id, catalog_item_id, status, namespace, data)
                       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)""",
                    session.session_id, session.request_id, session.tenant_id,
                    session.catalog_item_id, session.status.value, session.namespace, data,
                )

    def get(self, session_id: str) -> Optional[LabSession]:
        pool = get_pool()
        if not pool:
            return None
        return _run(self._get(pool, session_id))

    async def _get(self, pool, session_id: str) -> Optional[LabSession]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM lab_sessions WHERE session_id = $1", session_id
            )
            if row:
                return LabSession.model_validate(json.loads(row["data"]))
        return None

    def list_all(self) -> List[LabSession]:
        pool = get_pool()
        if not pool:
            return []
        return _run(self._list_all(pool))

    async def _list_all(self, pool) -> List[LabSession]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT data FROM lab_sessions")
            return [LabSession.model_validate(json.loads(r["data"])) for r in rows]

    def list_by_tenant(self, tenant_id: str) -> List[LabSession]:
        pool = get_pool()
        if not pool:
            return []
        return _run(self._list_by_tenant(pool, tenant_id))

    async def _list_by_tenant(self, pool, tenant_id: str) -> List[LabSession]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data FROM lab_sessions WHERE tenant_id = $1", tenant_id
            )
            return [LabSession.model_validate(json.loads(r["data"])) for r in rows]


class PostgresRequestStore:
    def save(self, request: LabRequest) -> None:
        pool = get_pool()
        if not pool:
            return
        _run(self._save(pool, request))

    async def _save(self, pool, request: LabRequest) -> None:
        data = json.dumps(request.model_dump(mode="json"))
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT request_id FROM lab_requests WHERE request_id = $1",
                request.request_id,
            )
            if existing:
                await conn.execute(
                    """UPDATE lab_requests
                       SET status = $1, data = $2::jsonb
                       WHERE request_id = $3""",
                    request.status.value, data, request.request_id,
                )
            else:
                await conn.execute(
                    """INSERT INTO lab_requests
                       (request_id, tenant_id, catalog_item_id, status, data)
                       VALUES ($1, $2, $3, $4, $5::jsonb)""",
                    request.request_id, request.tenant_id,
                    request.catalog_item_id, request.status.value, data,
                )

    def get(self, request_id: str) -> Optional[LabRequest]:
        pool = get_pool()
        if not pool:
            return None
        return _run(self._get(pool, request_id))

    async def _get(self, pool, request_id: str) -> Optional[LabRequest]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM lab_requests WHERE request_id = $1", request_id
            )
            if row:
                return LabRequest.model_validate(json.loads(row["data"]))
        return None

    def list_all(self) -> List[LabRequest]:
        pool = get_pool()
        if not pool:
            return []
        return _run(self._list_all(pool))

    async def _list_all(self, pool) -> List[LabRequest]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT data FROM lab_requests")
            return [LabRequest.model_validate(json.loads(r["data"])) for r in rows]


class PostgresPlanStore:
    def save(self, plan: ProvisioningPlan) -> None:
        pool = get_pool()
        if not pool:
            return
        _run(self._save(pool, plan))

    async def _save(self, pool, plan: ProvisioningPlan) -> None:
        data = json.dumps(plan.model_dump(mode="json"))
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO provisioning_plans (plan_id, request_id, data)
                   VALUES ($1, $2, $3::jsonb)
                   ON CONFLICT (plan_id) DO UPDATE SET data = $3::jsonb""",
                plan.plan_id, plan.request_id, data,
            )


class PostgresShowbackStore:
    def save(self, record: ShowbackRecord) -> None:
        pool = get_pool()
        if not pool:
            return
        _run(self._save(pool, record))

    async def _save(self, pool, record: ShowbackRecord) -> None:
        data = json.dumps(record.model_dump(mode="json"))
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO showback_records (showback_id, tenant_id, session_id, data)
                   VALUES ($1, $2, $3, $4::jsonb)
                   ON CONFLICT (showback_id) DO NOTHING""",
                record.showback_id, record.tenant_id, record.session_id, data,
            )

    def get(self, session_id: str) -> Optional[ShowbackRecord]:
        pool = get_pool()
        if not pool:
            return None
        return _run(self._get(pool, session_id))

    async def _get(self, pool, session_id: str) -> Optional[ShowbackRecord]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM showback_records WHERE session_id = $1", session_id
            )
            if row:
                return ShowbackRecord.model_validate(json.loads(row["data"]))
        return None


class PostgresCatalogStore:
    def save(self, item: CatalogItem) -> None:
        pool = get_pool()
        if not pool:
            return
        _run(self._save(pool, item))

    async def _save(self, pool, item: CatalogItem) -> None:
        data = json.dumps(item.model_dump(mode="json"))
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT catalog_item_id FROM catalog_items_custom WHERE catalog_item_id = $1",
                item.catalog_item_id,
            )
            if existing:
                await conn.execute(
                    """UPDATE catalog_items_custom
                       SET data = $1::jsonb, updated_at = NOW()
                       WHERE catalog_item_id = $2""",
                    data, item.catalog_item_id,
                )
            else:
                await conn.execute(
                    """INSERT INTO catalog_items_custom (catalog_item_id, data)
                       VALUES ($1, $2::jsonb)""",
                    item.catalog_item_id, data,
                )

    def list_all(self) -> List[CatalogItem]:
        pool = get_pool()
        if not pool:
            return []
        return _run(self._list_all(pool))

    async def _list_all(self, pool) -> List[CatalogItem]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT data FROM catalog_items_custom")
            return [CatalogItem.model_validate(json.loads(r["data"])) for r in rows]
