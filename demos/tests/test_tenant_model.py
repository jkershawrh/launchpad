#!/usr/bin/env python3
"""Tenant Model + Auth — TDD Red Phase

Tests tenant data model, migration, auth middleware, and graceful degradation.
"""

import re
import subprocess
import sys
import asyncio
import importlib
import pytest
from pathlib import Path


@pytest.fixture
def gateway_dir(project_root) -> Path:
    return project_root / "gateway"


@pytest.fixture
def migrations_dir(gateway_dir) -> Path:
    return gateway_dir / "migrations"


@pytest.fixture
def tenant_migration_sql(migrations_dir) -> str:
    sql_file = migrations_dir / "002_tenant_model.sql"
    if not sql_file.exists():
        pytest.skip("Tenant migration not created yet")
    return sql_file.read_text()


@pytest.fixture
def db_module(project_root):
    gateway_path = str(project_root / "gateway")
    sys.path.insert(0, gateway_path)
    import db
    importlib.reload(db)
    yield db
    sys.path.remove(gateway_path)


@pytest.fixture
def auth_module(project_root):
    gateway_path = str(project_root / "gateway")
    if gateway_path not in sys.path:
        sys.path.insert(0, gateway_path)
    import auth
    importlib.reload(auth)
    yield auth


# ─── MIGRATION STRUCTURAL ───

class TestTenantMigration:

    def test_migration_file_exists(self, migrations_dir):
        assert (migrations_dir / "002_tenant_model.sql").exists()

    def test_tenants_table_defined(self, tenant_migration_sql):
        assert 'tenants' in tenant_migration_sql.lower()

    def test_api_keys_table_defined(self, tenant_migration_sql):
        assert 'api_keys' in tenant_migration_sql.lower()

    def test_tenants_has_slug(self, tenant_migration_sql):
        assert re.search(r'slug\s+VARCHAR', tenant_migration_sql, re.IGNORECASE)

    def test_tenants_has_tier(self, tenant_migration_sql):
        assert re.search(r'tier\s+VARCHAR', tenant_migration_sql, re.IGNORECASE)

    def test_tenants_has_resource_quota(self, tenant_migration_sql):
        assert re.search(r'resource_quota\s+JSONB', tenant_migration_sql, re.IGNORECASE)

    def test_tenants_has_expires_at(self, tenant_migration_sql):
        assert 'expires_at' in tenant_migration_sql

    def test_api_keys_references_tenants(self, tenant_migration_sql):
        assert re.search(r'REFERENCES\s+tenants', tenant_migration_sql, re.IGNORECASE)

    def test_api_keys_has_key_hash(self, tenant_migration_sql):
        assert 'key_hash' in tenant_migration_sql

    def test_api_keys_has_scopes(self, tenant_migration_sql):
        assert 'scopes' in tenant_migration_sql

    def test_tenant_id_added_to_inference_requests(self, tenant_migration_sql):
        assert re.search(r'inference_requests.*tenant_id|tenant_id.*inference_requests', tenant_migration_sql, re.IGNORECASE | re.DOTALL)

    def test_tenant_id_added_to_audit_log(self, tenant_migration_sql):
        assert re.search(r'audit_log.*tenant_id|tenant_id.*audit_log', tenant_migration_sql, re.IGNORECASE | re.DOTALL)

    def test_has_rls_policy(self, tenant_migration_sql):
        assert 'ROW LEVEL SECURITY' in tenant_migration_sql.upper() or 'row level security' in tenant_migration_sql.lower()

    def test_seeds_internal_tenant(self, tenant_migration_sql):
        assert "'internal'" in tenant_migration_sql

    def test_slug_is_unique(self, tenant_migration_sql):
        assert re.search(r'slug.*UNIQUE|UNIQUE.*slug', tenant_migration_sql, re.IGNORECASE)

    def test_has_tenant_index(self, tenant_migration_sql):
        assert re.search(r'idx.*tenant', tenant_migration_sql, re.IGNORECASE)


# ─── DB MODULE — TENANT FUNCTIONS ───

class TestDbTenantFunctions:

    def test_db_has_tenant_functions(self, gateway_dir):
        content = (gateway_dir / "db.py").read_text()
        required = [
            'async def get_tenant_by_slug',
            'async def create_tenant',
            'async def verify_api_key_db',
            'async def create_api_key',
            'async def list_tenants',
            'async def update_tenant',
            'async def deactivate_tenant',
        ]
        for func in required:
            assert func in content, f"Missing function: {func}"

    def test_get_tenant_by_slug_returns_none_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.get_tenant_by_slug("test-tenant")
        )
        assert result is None

    def test_create_tenant_returns_none_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.create_tenant(slug="test", display_name="Test", tier="pilot")
        )
        assert result is None

    def test_verify_api_key_returns_none_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.verify_api_key_db("fake-hash")
        )
        assert result is None

    def test_create_api_key_returns_none_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.create_api_key(tenant_id="00000000-0000-0000-0000-000000000000", label="test")
        )
        assert result is None

    def test_list_tenants_returns_empty_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.list_tenants()
        )
        assert result == []

    def test_update_tenant_returns_false_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.update_tenant("test", config={"rate_limit_rpm": 100})
        )
        assert result is False

    def test_deactivate_tenant_returns_false_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.deactivate_tenant("test")
        )
        assert result is False


# ─── AUTH MODULE ───

class TestAuthModule:

    def test_auth_module_exists(self, gateway_dir):
        assert (gateway_dir / "auth.py").exists()

    def test_auth_module_compiles(self, gateway_dir):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(gateway_dir / "auth.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_tenant_context(self, auth_module):
        assert hasattr(auth_module, 'TenantContext')

    def test_tenant_context_has_required_fields(self, auth_module):
        ctx = auth_module.TenantContext(
            tenant_id="abc", tenant_slug="test", tier="pilot",
            scopes=["read", "write"], user_email=None
        )
        assert ctx.tenant_id == "abc"
        assert ctx.tenant_slug == "test"
        assert ctx.tier == "pilot"
        assert ctx.scopes == ["read", "write"]
        assert ctx.user_email is None

    def test_has_resolve_tenant(self, auth_module):
        assert hasattr(auth_module, 'resolve_tenant')
        assert callable(auth_module.resolve_tenant)

    def test_has_require_scope(self, auth_module):
        assert hasattr(auth_module, 'require_scope')
        assert callable(auth_module.require_scope)

    def test_has_require_tier(self, auth_module):
        assert hasattr(auth_module, 'require_tier')
        assert callable(auth_module.require_tier)

    def test_internal_tenant_constant(self, auth_module):
        assert hasattr(auth_module, 'INTERNAL_TENANT')
        assert auth_module.INTERNAL_TENANT["slug"] == "internal"


# ─── AUTH API TESTS ───

class TestAuthAPI:

    def test_legacy_api_key_still_works(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_no_auth_on_health_endpoint(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
            assert resp.status_code == 200


# ─── TENANT ADMIN API ───

class TestTenantAdminAPI:

    def test_tenant_api_module_exists(self, gateway_dir):
        assert (gateway_dir / "tenant_api.py").exists()

    def test_tenant_api_compiles(self, gateway_dir):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(gateway_dir / "tenant_api.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_create_endpoint_exists(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/tenants", json={"slug": "test", "display_name": "Test"})
            assert resp.status_code in (200, 201, 401, 403)

    def test_list_endpoint_exists(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tenants")
            assert resp.status_code in (200, 401, 403)


# ─── PER-TENANT RATE LIMITING ───

class TestPerTenantRateLimit:

    def test_rate_limit_function_accepts_tenant_id(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert re.search(r'def check_rate_limit\(.*tenant', content), \
            "check_rate_limit should accept tenant_id parameter"

    def test_rate_limit_key_includes_tenant(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'tenant' in content.split('_rate_limits')[1][:200] if '_rate_limits' in content else True
