"""
Data-access layer using psycopg2 (synchronous).

Each store class uses synchronous psycopg2 connections from a shared
DATABASE_URL. When DATABASE_URL is not set, all operations are no-ops
that return None or empty lists, allowing in-memory fallback.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from typing import List, Optional

from app.domain.feedback import ProvisioningOutcome
from app.domain.models import (
    CatalogItem,
    LabRequest,
    LabSession,
    ProvisioningPlan,
    ShowbackRecord,
    Tenant,
    Workshop,
)
from app.storage.database import get_database_url

logger = logging.getLogger("launchpad.stores")


def _get_sync_conn():
    """Get a synchronous psycopg2 connection."""
    url = get_database_url()
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url, connect_timeout=5)
    except Exception as e:
        logger.warning("psycopg2 connect failed: %s", e)
        return None


def _decode_json(value: Any) -> Any:
    """Normalize JSONB values returned by different psycopg2 configurations."""
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


class PostgresTenantStore:
    def save(self, tenant: Tenant) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(tenant.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tenants (tenant_id, data)
                       VALUES (%s, %s::jsonb)
                       ON CONFLICT (tenant_id) DO UPDATE SET data = %s::jsonb""",
                    (tenant.tenant_id, data, data),
                )
            conn.commit()
        except Exception as e:
            logger.warning("DB save tenant error: %s", e)
            conn.rollback()
        finally:
            conn.close()

    def get(self, tenant_id: str) -> Optional[Tenant]:
        conn = _get_sync_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM tenants WHERE tenant_id = %s", (tenant_id,))
                row = cur.fetchone()
                if row:
                    return Tenant.model_validate(_decode_json(row[0]))
            return None
        except Exception as e:
            logger.warning("DB get tenant error: %s", e)
            return None
        finally:
            conn.close()

    def list_all(self) -> List[Tenant]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM tenants")
                rows = cur.fetchall()
                return [Tenant.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list tenants error: %s", e)
            return []
        finally:
            conn.close()


class PostgresSessionStore:
    def save(self, session: LabSession) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(session.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id FROM lab_sessions WHERE session_id = %s",
                    (session.session_id,),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """UPDATE lab_sessions
                           SET status = %s, namespace = %s, data = %s::jsonb, updated_at = NOW()
                           WHERE session_id = %s""",
                        (session.status.value, session.namespace, data, session.session_id),
                    )
                else:
                    cur.execute(
                        """INSERT INTO lab_sessions
                           (session_id, request_id, tenant_id, catalog_item_id, status, namespace, data)
                           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
                        (session.session_id, session.request_id, session.tenant_id,
                         session.catalog_item_id, session.status.value, session.namespace, data),
                    )
            conn.commit()
        except Exception as e:
            logger.warning("DB save session error: %s", e)
            conn.rollback()
        finally:
            conn.close()


    def get(self, session_id: str) -> Optional[LabSession]:
        conn = _get_sync_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM lab_sessions WHERE session_id = %s", (session_id,))
                row = cur.fetchone()
                if row:
                    return LabSession.model_validate(_decode_json(row[0]))
            return None
        except Exception as e:
            logger.warning("DB get session error: %s", e)
            return None
        finally:
            conn.close()

    def list_all(self) -> List[LabSession]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM lab_sessions")
                rows = cur.fetchall()
                return [LabSession.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list sessions error: %s", e)
            return []
        finally:
            conn.close()

    def list_by_tenant(self, tenant_id: str) -> List[LabSession]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM lab_sessions WHERE tenant_id = %s", (tenant_id,)
                )
                rows = cur.fetchall()
                return [LabSession.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list sessions by tenant error: %s", e)
            return []
        finally:
            conn.close()


class PostgresWorkshopStore:
    def save(self, workshop: Workshop) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(workshop.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO workshops
                       (workshop_id, tenant_id, catalog_item_id, status,
                        idempotency_key, order_fingerprint, data)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                       ON CONFLICT (workshop_id) DO UPDATE SET
                         status = EXCLUDED.status,
                         data = EXCLUDED.data,
                         updated_at = NOW()""",
                    (
                        workshop.workshop_id,
                        workshop.tenant_id,
                        workshop.catalog_item_id,
                        workshop.status.value,
                        workshop.idempotency_key,
                        workshop.order_fingerprint,
                        data,
                    ),
                )
            conn.commit()
        except Exception as e:
            logger.warning("DB save workshop error: %s", e)
            conn.rollback()
        finally:
            conn.close()

    def get(self, workshop_id: str) -> Optional[Workshop]:
        conn = _get_sync_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM workshops WHERE workshop_id = %s",
                    (workshop_id,),
                )
                row = cur.fetchone()
                return Workshop.model_validate(_decode_json(row[0])) if row else None
        except Exception as e:
            logger.warning("DB get workshop error: %s", e)
            return None
        finally:
            conn.close()

    def list_all(self) -> List[Workshop]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM workshops")
                return [
                    Workshop.model_validate(_decode_json(row[0]))
                    for row in cur.fetchall()
                ]
        except Exception as e:
            logger.warning("DB list workshops error: %s", e)
            return []
        finally:
            conn.close()


class PostgresRequestStore:
    def save(self, request: LabRequest) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(request.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT request_id FROM lab_requests WHERE request_id = %s",
                    (request.request_id,),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """UPDATE lab_requests
                           SET status = %s, data = %s::jsonb
                           WHERE request_id = %s""",
                        (request.status.value, data, request.request_id),
                    )
                else:
                    cur.execute(
                        """INSERT INTO lab_requests
                           (request_id, tenant_id, catalog_item_id, status, data)
                           VALUES (%s, %s, %s, %s, %s::jsonb)""",
                        (request.request_id, request.tenant_id,
                         request.catalog_item_id, request.status.value, data),
                    )
            conn.commit()
        except Exception as e:
            logger.warning("DB save request error: %s", e)
            conn.rollback()
        finally:
            conn.close()

    def get(self, request_id: str) -> Optional[LabRequest]:
        conn = _get_sync_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM lab_requests WHERE request_id = %s", (request_id,))
                row = cur.fetchone()
                if row:
                    return LabRequest.model_validate(_decode_json(row[0]))
            return None
        except Exception as e:
            logger.warning("DB get request error: %s", e)
            return None
        finally:
            conn.close()

    def list_all(self) -> List[LabRequest]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM lab_requests")
                rows = cur.fetchall()
                return [LabRequest.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list requests error: %s", e)
            return []
        finally:
            conn.close()


class PostgresPlanStore:
    def save(self, plan: ProvisioningPlan) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(plan.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO provisioning_plans (plan_id, request_id, data)
                       VALUES (%s, %s, %s::jsonb)
                       ON CONFLICT (plan_id) DO UPDATE SET data = %s::jsonb""",
                    (plan.plan_id, plan.request_id, data, data),
                )
            conn.commit()
        except Exception as e:
            logger.warning("DB save plan error: %s", e)
            conn.rollback()
        finally:
            conn.close()


class PostgresShowbackStore:
    def save(self, record: ShowbackRecord) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(record.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO showback_records (showback_id, tenant_id, session_id, data)
                       VALUES (%s, %s, %s, %s::jsonb)
                       ON CONFLICT (showback_id) DO NOTHING""",
                    (record.showback_id, record.tenant_id, record.session_id, data),
                )
            conn.commit()
        except Exception as e:
            logger.warning("DB save showback error: %s", e)
            conn.rollback()
        finally:
            conn.close()

    def get(self, session_id: str) -> Optional[ShowbackRecord]:
        conn = _get_sync_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM showback_records WHERE session_id = %s", (session_id,)
                )
                row = cur.fetchone()
                if row:
                    return ShowbackRecord.model_validate(_decode_json(row[0]))
            return None
        except Exception as e:
            logger.warning("DB get showback error: %s", e)
            return None
        finally:
            conn.close()


class PostgresCatalogStore:
    def save(self, item: CatalogItem) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(item.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT catalog_item_id FROM catalog_items_custom WHERE catalog_item_id = %s",
                    (item.catalog_item_id,),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """UPDATE catalog_items_custom
                           SET data = %s::jsonb, updated_at = NOW()
                           WHERE catalog_item_id = %s""",
                        (data, item.catalog_item_id),
                    )
                else:
                    cur.execute(
                        """INSERT INTO catalog_items_custom (catalog_item_id, data)
                           VALUES (%s, %s::jsonb)""",
                        (item.catalog_item_id, data),
                    )
            conn.commit()
        except Exception as e:
            logger.warning("DB save catalog item error: %s", e)
            conn.rollback()
        finally:
            conn.close()

    def list_all(self) -> List[CatalogItem]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM catalog_items_custom")
                rows = cur.fetchall()
                return [CatalogItem.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list catalog items error: %s", e)
            return []
        finally:
            conn.close()


class PostgresOutcomeStore:
    def save(self, outcome: ProvisioningOutcome) -> None:
        conn = _get_sync_conn()
        if not conn:
            return
        try:
            data = json.dumps(outcome.model_dump(mode="json"))
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO provisioning_outcomes
                       (outcome_id, session_id, request_id, catalog_item_id, cluster_name, hardware_profile, data)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                       ON CONFLICT (outcome_id) DO NOTHING""",
                    (outcome.outcome_id, outcome.session_id, outcome.request_id,
                     outcome.catalog_item_id, outcome.cluster_name, outcome.hardware_profile, data),
                )
            conn.commit()
        except Exception as e:
            logger.warning("DB save outcome error: %s", e)
            conn.rollback()
        finally:
            conn.close()

    def list_by_catalog(self, catalog_item_id: str) -> List[ProvisioningOutcome]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM provisioning_outcomes WHERE catalog_item_id = %s",
                    (catalog_item_id,),
                )
                rows = cur.fetchall()
                return [ProvisioningOutcome.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list outcomes by catalog error: %s", e)
            return []
        finally:
            conn.close()

    def list_by_cluster(self, cluster_name: str) -> List[ProvisioningOutcome]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM provisioning_outcomes WHERE cluster_name = %s",
                    (cluster_name,),
                )
                rows = cur.fetchall()
                return [ProvisioningOutcome.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list outcomes by cluster error: %s", e)
            return []
        finally:
            conn.close()

    def list_all(self) -> List[ProvisioningOutcome]:
        conn = _get_sync_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM provisioning_outcomes ORDER BY created_at DESC LIMIT 1000")
                rows = cur.fetchall()
                return [ProvisioningOutcome.model_validate(_decode_json(r[0])) for r in rows]
        except Exception as e:
            logger.warning("DB list all outcomes error: %s", e)
            return []
        finally:
            conn.close()
