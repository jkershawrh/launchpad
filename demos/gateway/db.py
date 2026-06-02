"""
Database layer for the Inference Gateway

Provides async PostgreSQL connection, migration runner,
query helpers, and config seeding from YAML.
Graceful degradation: gateway works without DB.
"""

import os
import json
import uuid
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_pool = None


async def connect():
    """Initialize the connection pool. No-op if DATABASE_URL is not set."""
    global _pool
    if not DATABASE_URL:
        logger.info("DATABASE_URL not set — running without persistence")
        return False
    try:
        import asyncpg
    except ImportError:
        logger.warning("asyncpg not installed — running without persistence")
        return False
    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=2, max_size=10,
            server_settings={'statement_timeout': '30000'}
        )
        logger.info("Connected to PostgreSQL")
        return True
    except Exception as e:
        logger.warning("Failed to connect to PostgreSQL: %s — running without persistence", e)
        _pool = None
        return False


async def disconnect():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def is_connected() -> bool:
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False


async def run_migrations():
    """Run all migration SQL files in order, tracking applied migrations."""
    if not _pool:
        return
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with _pool.acquire() as conn:
        # Ensure applied_migrations tracking table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """)
        for sql_file in sql_files:
            # Check if already applied
            already = await conn.fetchval(
                "SELECT COUNT(*) FROM applied_migrations WHERE filename = $1",
                sql_file.name
            )
            if already:
                logger.debug("Migration %s already applied", sql_file.name)
                continue
            sql = sql_file.read_text()
            try:
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO applied_migrations (filename) VALUES ($1)",
                    sql_file.name
                )
                logger.info("Applied migration: %s", sql_file.name)
            except Exception as e:
                err_msg = str(e).lower()
                if 'already exists' in err_msg or 'duplicate' in err_msg:
                    logger.debug("Migration %s already applied", sql_file.name)
                else:
                    logger.error("Migration %s failed: %s", sql_file.name, e)
                    raise


async def seed_from_config(config: dict):
    """Seed backends and routing_rules from config.yaml if tables are empty."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM backends")
        if count > 0:
            logger.info("Backends table already populated (%d rows), skipping seed", count)
            return

        logger.info("Seeding backends and routing rules from config.yaml")
        backend_ids = {}
        for b in config.get('backends', []):
            if 'name' not in b or 'url' not in b:
                logger.warning("Skipping backend missing name or url: %s", b)
                continue
            row = await conn.fetchrow(
                """INSERT INTO backends (name, url, accelerator, capabilities, cost_per_1k_tokens, max_concurrent)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (name) DO NOTHING
                   RETURNING id""",
                b['name'], b['url'], b.get('accelerator', ''),
                b.get('capabilities', []), b.get('cost_per_1k_tokens', 0.0),
                b.get('max_concurrent', 10)
            )
            if row:
                backend_ids[b['name']] = row['id']
                await _audit(conn, 'backends', row['id'], 'create', b)

        for r in config.get('routes', []):
            backend_name = r.get('backend', r.get('default_backend', ''))
            backend_id = backend_ids.get(backend_name)
            if backend_id is None:
                logger.warning("Backend '%s' not found, skipping route", backend_name)
                continue
            condition_type = 'size_based' if 'conditions' in r else 'static'
            condition_json = json.dumps(r.get('conditions')) if 'conditions' in r else None
            await conn.execute(
                """INSERT INTO routing_rules (task, backend_id, condition_type, condition_json, reason)
                   VALUES ($1, $2, $3, $4, $5)""",
                r['task'], backend_id, condition_type, condition_json, r.get('reason', '')
            )

        logger.info("Seeded %d backends, %d routing rules",
                     len(backend_ids), len(config.get('routes', [])))


async def insert_request(
    task: str, backend: str, accelerator: str, status: str,
    latency_ms: float, cost_estimate: float, reason: str,
    model: str = "", model_size_b: float = 0, error_detail: str = ""
) -> Optional[str]:
    """Insert a routing request record. Returns request ID or None."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO inference_requests
                   (task, model, model_size_b, backend, accelerator, status,
                    latency_ms, cost_estimate, reason, error_detail)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                   RETURNING id""",
                task, model, model_size_b, backend, accelerator, status,
                latency_ms, cost_estimate, reason, error_detail
            )
            return str(row['id'])
    except Exception as e:
        logger.error("Failed to insert request: %s", e, exc_info=True)
        return None


async def insert_governance_decision(
    request_id: Optional[str], source: str, intent: str,
    risk_score: float, risk_level: str, decision: str,
    reason: str, evidence: dict
) -> Optional[str]:
    """Insert a governance decision. Returns decision ID or None."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            req_uuid = uuid.UUID(request_id) if request_id else None
            row = await conn.fetchrow(
                """INSERT INTO governance_decisions
                   (request_id, source, intent, risk_score, risk_level,
                    decision, reason, evidence)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   RETURNING id""",
                req_uuid, source, intent, risk_score, risk_level,
                decision, reason, json.dumps(evidence)
            )
            return str(row['id'])
    except Exception as e:
        logger.error("Failed to insert governance decision: %s", e, exc_info=True)
        return None


async def get_request_by_id(request_id: str) -> Optional[dict]:
    """Get a single request by UUID."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM inference_requests WHERE id = $1",
                uuid.UUID(request_id)
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get request %s: %s", request_id, e)
        return None


async def get_decision_by_id(decision_id: str) -> Optional[dict]:
    """Get a single governance decision by UUID."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM governance_decisions WHERE id = $1",
                uuid.UUID(decision_id)
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get decision %s: %s", decision_id, e)
        return None


async def get_requests(
    task: str = None, backend: str = None, status: str = None,
    limit: int = 50, offset: int = 0
) -> list:
    """Query inference requests with optional filters."""
    if not _pool:
        return []
    conditions = []
    params = []
    idx = 1
    if task:
        conditions.append(f"task = ${idx}")
        params.append(task)
        idx += 1
    if backend:
        conditions.append(f"backend = ${idx}")
        params.append(backend)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT * FROM inference_requests {where}
                ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}"""
    params.extend([limit, offset])

    async with _pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


async def get_decisions(
    decision: str = None, source: str = None,
    limit: int = 50, offset: int = 0
) -> list:
    """Query governance decisions with optional filters."""
    if not _pool:
        return []
    conditions = []
    params = []
    idx = 1
    if decision:
        conditions.append(f"decision = ${idx}")
        params.append(decision)
        idx += 1
    if source:
        conditions.append(f"source = ${idx}")
        params.append(source)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT * FROM governance_decisions {where}
                ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}"""
    params.extend([limit, offset])

    async with _pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


async def get_backends_from_db() -> list:
    """Get all backends from database."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM backends ORDER BY name")
        return [dict(r) for r in rows]


async def get_routing_rules() -> list:
    """Get active routing rules."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM routing_rules WHERE active = TRUE ORDER BY task, priority"
        )
        return [dict(r) for r in rows]


async def get_cost_summary(days: int = 30) -> list:
    """Get cost breakdown by backend and task for the last N days."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT backend, task,
                      COUNT(*) as request_count,
                      SUM(cost_estimate) as total_cost,
                      AVG(latency_ms) as avg_latency_ms
               FROM inference_requests
               WHERE created_at > NOW() - make_interval(days => $1)
                 AND status = 'success'
               GROUP BY backend, task
               ORDER BY total_cost DESC""",
            days
        )
        return [dict(r) for r in rows]


async def get_routing_distribution(days: int = 7) -> list:
    """Percentage of requests routed to each backend."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT backend, COUNT(*) as count,
                      ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER(), 0) * 100, 1) as pct
               FROM inference_requests
               WHERE created_at > NOW() - make_interval(days => $1)
               GROUP BY backend ORDER BY count DESC""",
            days
        )
        return [dict(r) for r in rows]


async def get_latency_percentiles(days: int = 7) -> list:
    """Latency percentiles by backend."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT backend,
                      PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) as p50_ms,
                      PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_ms,
                      PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99_ms,
                      COUNT(*) as sample_count
               FROM inference_requests
               WHERE created_at > NOW() - make_interval(days => $1)
                 AND status = 'success'
               GROUP BY backend ORDER BY backend""",
            days
        )
        return [dict(r) for r in rows]


async def get_cost_by_task(days: int = 30) -> list:
    """Cost breakdown by task type."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT task,
                      COUNT(*) as request_count,
                      SUM(cost_estimate) as total_cost,
                      AVG(cost_estimate) as avg_cost_per_request
               FROM inference_requests
               WHERE created_at > NOW() - make_interval(days => $1)
                 AND status = 'success'
               GROUP BY task ORDER BY total_cost DESC""",
            days
        )
        return [dict(r) for r in rows]


async def get_governance_summary(days: int = 30) -> list:
    """Summary of governance decisions."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT decision, COUNT(*) as count,
                      ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER(), 0) * 100, 1) as pct
               FROM governance_decisions
               WHERE created_at > NOW() - make_interval(days => $1)
               GROUP BY decision ORDER BY count DESC""",
            days
        )
        return [dict(r) for r in rows]


async def approve_decision(decision_id: str, approved_by: str) -> bool:
    """Record human approval for a governance decision."""
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE governance_decisions
                   SET approved_by = $1, approved_at = NOW()
                   WHERE id = $2""",
                approved_by, uuid.UUID(decision_id)
            )
            if result == 'UPDATE 0':
                return False
            await _audit(conn, 'governance_decisions', uuid.UUID(decision_id), 'approve',
                         {'approved_by': approved_by})
            return True
    except Exception as e:
        logger.error("Failed to approve decision: %s", e, exc_info=True)
        return False


async def _audit(conn, entity_type: str, entity_id, action: str, changes: dict):
    """Write an audit log entry using the caller's connection."""
    try:
        await conn.execute(
            """INSERT INTO audit_log (entity_type, entity_id, action, changes)
               VALUES ($1, $2, $3, $4)""",
            entity_type, entity_id, action, json.dumps(changes, default=str)
        )
    except Exception as e:
        logger.error("Failed to write audit log: %s", e)


# ─── Tenant Management ───

async def get_tenant_by_slug(slug: str) -> Optional[dict]:
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tenants WHERE slug = $1 AND active = TRUE", slug
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get tenant %s: %s", slug, e)
        return None


async def get_tenant_by_id(tenant_id: str) -> Optional[dict]:
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tenants WHERE id = $1", uuid.UUID(tenant_id)
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get tenant %s: %s", tenant_id, e)
        return None


async def create_tenant(slug: str, display_name: str, tier: str = "pilot",
                        resource_quota: dict = None, config: dict = None) -> Optional[str]:
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO tenants (slug, display_name, tier, resource_quota, config)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                slug, display_name, tier,
                json.dumps(resource_quota or {}),
                json.dumps(config or {})
            )
            await _audit(conn, 'tenants', row['id'], 'create',
                         {'slug': slug, 'tier': tier})
            return str(row['id'])
    except Exception as e:
        logger.error("Failed to create tenant: %s", e)
        return None


async def list_tenants() -> list:
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, slug, display_name, tier, active, created_at, expires_at FROM tenants ORDER BY slug"
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to list tenants: %s", e)
        return []


async def update_tenant(slug: str, **kwargs) -> bool:
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            sets = []
            params = []
            idx = 1
            for k, v in kwargs.items():
                if k in ('display_name', 'tier', 'expires_at'):
                    sets.append(f"{k} = ${idx}")
                    params.append(v)
                    idx += 1
                elif k in ('resource_quota', 'config'):
                    sets.append(f"{k} = ${idx}")
                    params.append(json.dumps(v))
                    idx += 1
            if not sets:
                return False
            params.append(slug)
            result = await conn.execute(
                f"UPDATE tenants SET {', '.join(sets)} WHERE slug = ${idx}", *params
            )
            return result != 'UPDATE 0'
    except Exception as e:
        logger.error("Failed to update tenant %s: %s", slug, e)
        return False


async def deactivate_tenant(slug: str) -> bool:
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE tenants SET active = FALSE WHERE slug = $1", slug
            )
            return result != 'UPDATE 0'
    except Exception as e:
        logger.error("Failed to deactivate tenant %s: %s", slug, e)
        return False


async def verify_api_key_db(key_hash: str) -> Optional[dict]:
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT k.tenant_id, k.scopes, t.slug as tenant_slug, t.tier
                   FROM api_keys k JOIN tenants t ON k.tenant_id = t.id
                   WHERE k.key_hash = $1 AND k.active = TRUE AND t.active = TRUE
                   AND (k.expires_at IS NULL OR k.expires_at > NOW())""",
                key_hash
            )
            if row:
                return {"tenant_id": str(row['tenant_id']), "tenant_slug": row['tenant_slug'],
                        "tier": row['tier'], "scopes": list(row['scopes'])}
            return None
    except Exception as e:
        logger.error("Failed to verify API key: %s", e)
        return None


async def create_api_key(tenant_id: str, label: str = "default",
                         key_hash: str = "", scopes: list = None) -> Optional[str]:
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO api_keys (tenant_id, key_hash, label, scopes)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                uuid.UUID(tenant_id), key_hash, label, scopes or ["read", "write"]
            )
            return str(row['id'])
    except Exception as e:
        logger.error("Failed to create API key: %s", e)
        return None


async def set_tenant_context(conn, tenant_id: str):
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', tenant_id):
        raise ValueError(f"Invalid tenant_id format")
    await conn.execute("SET app.current_tenant_id = $1", tenant_id)


# ─── Run Persistence ───

async def persist_run(run_id: str, run_type: str, status: str,
                      tenant_id: str = None, summary: dict = None) -> Optional[str]:
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            t_id = uuid.UUID(tenant_id) if tenant_id else None
            row = await conn.fetchrow(
                """INSERT INTO demo_runs (run_id, run_type, tenant_id, status, summary, completed_at)
                   VALUES ($1, $2, $3, $4, $5, NOW()) RETURNING id""",
                run_id, run_type, t_id, status, json.dumps(summary or {})
            )
            return str(row['id'])
    except Exception as e:
        logger.error("Failed to persist run %s: %s", run_id, e)
        return None


async def get_run_history(run_type: str = None, limit: int = 50) -> list:
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            if run_type:
                rows = await conn.fetch(
                    "SELECT * FROM demo_runs WHERE run_type = $1 ORDER BY completed_at DESC LIMIT $2",
                    run_type, limit
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM demo_runs ORDER BY completed_at DESC LIMIT $1", limit
                )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get run history: %s", e)
        return []


async def get_tenant_runs(tenant_id: str, limit: int = 50) -> list:
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM demo_runs WHERE tenant_id = $1 ORDER BY completed_at DESC LIMIT $2",
                uuid.UUID(tenant_id), limit
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get tenant runs: %s", e)
        return []


async def get_expired_tenants() -> list:
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT slug, display_name, expires_at FROM tenants WHERE active = TRUE AND expires_at < NOW()"
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get expired tenants: %s", e)
        return []
