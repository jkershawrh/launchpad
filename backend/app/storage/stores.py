from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domain.models import (
    CatalogItem,
    LabRequest,
    LabSession,
    ProvisioningPlan,
    ShowbackRecord,
    Tenant,
)
from app.storage.database import (
    catalog_items_custom_table,
    get_engine,
    lab_requests_table,
    lab_sessions_table,
    provisioning_plans_table,
    showback_records_table,
    tenants_table,
)


class PostgresTenantStore:
    def save(self, tenant: Tenant) -> None:
        engine = get_engine()
        if not engine:
            return
        with engine.begin() as conn:
            data = tenant.model_dump(mode="json")
            stmt = pg_insert(tenants_table).values(tenant_id=tenant.tenant_id, data=data)
            stmt = stmt.on_conflict_do_update(index_elements=["tenant_id"], set_={"data": data})
            conn.execute(stmt)

    def get(self, tenant_id: str) -> Optional[Tenant]:
        engine = get_engine()
        if not engine:
            return None
        with engine.connect() as conn:
            row = conn.execute(
                select(tenants_table.c.data).where(tenants_table.c.tenant_id == tenant_id)
            ).first()
            if row:
                return Tenant.model_validate(row[0])
        return None

    def list_all(self) -> List[Tenant]:
        engine = get_engine()
        if not engine:
            return []
        with engine.connect() as conn:
            rows = conn.execute(select(tenants_table.c.data)).fetchall()
            return [Tenant.model_validate(r[0]) for r in rows]


class PostgresSessionStore:
    def save(self, session: LabSession) -> None:
        engine = get_engine()
        if not engine:
            return
        data = session.model_dump(mode="json")
        with engine.begin() as conn:
            existing = conn.execute(
                select(lab_sessions_table.c.session_id)
                .where(lab_sessions_table.c.session_id == session.session_id)
            ).first()
            if existing:
                conn.execute(
                    update(lab_sessions_table)
                    .where(lab_sessions_table.c.session_id == session.session_id)
                    .values(
                        status=session.status.value,
                        namespace=session.namespace,
                        data=data,
                    )
                )
            else:
                conn.execute(
                    lab_sessions_table.insert().values(
                        session_id=session.session_id,
                        request_id=session.request_id,
                        tenant_id=session.tenant_id,
                        catalog_item_id=session.catalog_item_id,
                        status=session.status.value,
                        namespace=session.namespace,
                        data=data,
                    )
                )

    def get(self, session_id: str) -> Optional[LabSession]:
        engine = get_engine()
        if not engine:
            return None
        with engine.connect() as conn:
            row = conn.execute(
                select(lab_sessions_table.c.data)
                .where(lab_sessions_table.c.session_id == session_id)
            ).first()
            if row:
                return LabSession.model_validate(row[0])
        return None

    def list_all(self) -> List[LabSession]:
        engine = get_engine()
        if not engine:
            return []
        with engine.connect() as conn:
            rows = conn.execute(select(lab_sessions_table.c.data)).fetchall()
            return [LabSession.model_validate(r[0]) for r in rows]

    def list_by_tenant(self, tenant_id: str) -> List[LabSession]:
        engine = get_engine()
        if not engine:
            return []
        with engine.connect() as conn:
            rows = conn.execute(
                select(lab_sessions_table.c.data)
                .where(lab_sessions_table.c.tenant_id == tenant_id)
            ).fetchall()
            return [LabSession.model_validate(r[0]) for r in rows]


class PostgresRequestStore:
    def save(self, request: LabRequest) -> None:
        engine = get_engine()
        if not engine:
            return
        data = request.model_dump(mode="json")
        with engine.begin() as conn:
            existing = conn.execute(
                select(lab_requests_table.c.request_id)
                .where(lab_requests_table.c.request_id == request.request_id)
            ).first()
            if existing:
                conn.execute(
                    update(lab_requests_table)
                    .where(lab_requests_table.c.request_id == request.request_id)
                    .values(status=request.status.value, data=data)
                )
            else:
                conn.execute(
                    lab_requests_table.insert().values(
                        request_id=request.request_id,
                        tenant_id=request.tenant_id,
                        catalog_item_id=request.catalog_item_id,
                        status=request.status.value,
                        data=data,
                    )
                )

    def get(self, request_id: str) -> Optional[LabRequest]:
        engine = get_engine()
        if not engine:
            return None
        with engine.connect() as conn:
            row = conn.execute(
                select(lab_requests_table.c.data)
                .where(lab_requests_table.c.request_id == request_id)
            ).first()
            if row:
                return LabRequest.model_validate(row[0])
        return None

    def list_all(self) -> List[LabRequest]:
        engine = get_engine()
        if not engine:
            return []
        with engine.connect() as conn:
            rows = conn.execute(select(lab_requests_table.c.data)).fetchall()
            return [LabRequest.model_validate(r[0]) for r in rows]


class PostgresPlanStore:
    def save(self, plan: ProvisioningPlan) -> None:
        engine = get_engine()
        if not engine:
            return
        data = plan.model_dump(mode="json")
        with engine.begin() as conn:
            conn.execute(
                provisioning_plans_table.insert()
                .values(plan_id=plan.plan_id, request_id=plan.request_id, data=data)
            )


class PostgresShowbackStore:
    def save(self, record: ShowbackRecord) -> None:
        engine = get_engine()
        if not engine:
            return
        data = record.model_dump(mode="json")
        with engine.begin() as conn:
            conn.execute(
                showback_records_table.insert()
                .values(
                    showback_id=record.showback_id,
                    tenant_id=record.tenant_id,
                    session_id=record.session_id,
                    data=data,
                )
            )

    def get(self, session_id: str) -> Optional[ShowbackRecord]:
        engine = get_engine()
        if not engine:
            return None
        with engine.connect() as conn:
            row = conn.execute(
                select(showback_records_table.c.data)
                .where(showback_records_table.c.session_id == session_id)
            ).first()
            if row:
                return ShowbackRecord.model_validate(row[0])
        return None


class PostgresCatalogStore:
    def save(self, item: CatalogItem) -> None:
        engine = get_engine()
        if not engine:
            return
        data = item.model_dump(mode="json")
        with engine.begin() as conn:
            existing = conn.execute(
                select(catalog_items_custom_table.c.catalog_item_id)
                .where(catalog_items_custom_table.c.catalog_item_id == item.catalog_item_id)
            ).first()
            if existing:
                conn.execute(
                    update(catalog_items_custom_table)
                    .where(catalog_items_custom_table.c.catalog_item_id == item.catalog_item_id)
                    .values(data=data)
                )
            else:
                conn.execute(
                    catalog_items_custom_table.insert()
                    .values(catalog_item_id=item.catalog_item_id, data=data)
                )

    def list_all(self) -> List[CatalogItem]:
        engine = get_engine()
        if not engine:
            return []
        with engine.connect() as conn:
            rows = conn.execute(select(catalog_items_custom_table.c.data)).fetchall()
            return [CatalogItem.model_validate(r[0]) for r in rows]
