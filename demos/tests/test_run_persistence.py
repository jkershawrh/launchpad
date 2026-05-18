#!/usr/bin/env python3
"""Run Persistence — TDD for DB-backed run history."""

import re
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
def run_migration_sql(migrations_dir) -> str:
    sql_file = migrations_dir / "003_run_persistence.sql"
    if not sql_file.exists():
        pytest.skip("Run persistence migration not created yet")
    return sql_file.read_text()


@pytest.fixture
def db_module(project_root):
    gateway_path = str(project_root / "gateway")
    sys.path.insert(0, gateway_path)
    import db
    importlib.reload(db)
    yield db
    sys.path.remove(gateway_path)


# ─── MIGRATION ───

class TestRunMigration:

    def test_migration_exists(self, migrations_dir):
        assert (migrations_dir / "003_run_persistence.sql").exists()

    def test_demo_runs_table(self, run_migration_sql):
        assert 'demo_runs' in run_migration_sql.lower()

    def test_has_run_type(self, run_migration_sql):
        assert re.search(r'run_type\s+VARCHAR', run_migration_sql, re.IGNORECASE)

    def test_has_tenant_id(self, run_migration_sql):
        assert 'tenant_id' in run_migration_sql

    def test_has_status(self, run_migration_sql):
        assert re.search(r'status\s+VARCHAR', run_migration_sql, re.IGNORECASE)

    def test_has_summary_jsonb(self, run_migration_sql):
        assert re.search(r'summary\s+JSONB', run_migration_sql, re.IGNORECASE)

    def test_has_started_at(self, run_migration_sql):
        assert 'started_at' in run_migration_sql

    def test_has_completed_at(self, run_migration_sql):
        assert 'completed_at' in run_migration_sql

    def test_has_run_type_index(self, run_migration_sql):
        assert re.search(r'idx.*run_type|idx.*demo_runs', run_migration_sql, re.IGNORECASE)

    def test_has_tenant_index(self, run_migration_sql):
        assert re.search(r'idx.*tenant', run_migration_sql, re.IGNORECASE)


# ─── DB FUNCTIONS ───

class TestRunDbFunctions:

    def test_has_persist_run(self, gateway_dir):
        content = (gateway_dir / "db.py").read_text()
        assert 'async def persist_run' in content

    def test_has_get_run_history(self, gateway_dir):
        content = (gateway_dir / "db.py").read_text()
        assert 'async def get_run_history' in content

    def test_has_get_tenant_runs(self, gateway_dir):
        content = (gateway_dir / "db.py").read_text()
        assert 'async def get_tenant_runs' in content

    def test_persist_run_returns_none_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.persist_run(
                run_id="test-123", run_type="workload", status="complete",
                tenant_id=None, summary={"total": 25}
            )
        )
        assert result is None

    def test_get_run_history_returns_empty_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.get_run_history(run_type="workload", limit=10)
        )
        assert result == []

    def test_get_tenant_runs_returns_empty_without_db(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.get_tenant_runs(tenant_id="abc", limit=10)
        )
        assert result == []


# ─── ROUTER INTEGRATION ───

class TestRouterPersistence:

    def test_workload_run_persists_on_complete(self, gateway_dir):
        content = (gateway_dir / "router.py").read_text()
        assert 'persist_run' in content

    def test_run_history_endpoint_exists(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/v1/runs/history")
            assert resp.status_code in (200, 401)

    def test_tenant_runs_endpoint_exists(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/v1/runs/history?run_type=workload")
            assert resp.status_code in (200, 401)


# ─── CAPACITY + ALLOCATION ───

class TestCapacityEndpoints:

    def test_capacity_endpoint_exists(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/v1/capacity/overview")
            assert resp.status_code in (200, 401)

    def test_capacity_returns_tenant_data(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/v1/capacity/overview")
            if resp.status_code == 200:
                data = resp.json()
                assert "tenants" in data or "capacity" in data


class TestDemoAllocation:

    def test_has_check_tenant_expiry(self, gateway_dir):
        content = (gateway_dir / "db.py").read_text()
        assert 'async def check_tenant_expiry' in content or 'async def get_expired_tenants' in content

    def test_expired_tenants_returns_empty_without_db(self, db_module):
        func = getattr(db_module, 'get_expired_tenants', None) or getattr(db_module, 'check_tenant_expiry', None)
        assert func is not None
        result = asyncio.get_event_loop().run_until_complete(func())
        assert result == []


# ─── CONTENT VALIDATION ───

class TestContentValidation:

    def test_validation_module_exists(self, gateway_dir):
        assert (gateway_dir / "content_validator.py").exists()

    def test_validate_model_artifact(self, project_root):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        from content_validator import validate_artifact
        result = validate_artifact({"name": "test-model", "type": "model", "source": "partner"})
        assert "status" in result
        assert result["status"] in ("passed", "warning", "blocked")

    def test_validate_rejects_suspicious(self, project_root):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        from content_validator import validate_artifact
        result = validate_artifact({"name": "../../../etc/passwd", "type": "model", "source": "partner"})
        assert result["status"] == "blocked"

    def test_validation_endpoint_exists(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/content/validate", json={"name": "test-model", "type": "model", "source": "partner"})
            assert resp.status_code in (200, 401)


# ─── PUBLISHING HOUSE ───

class TestPublishingHouse:

    def test_gallery_endpoint_exists(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/v1/gallery/pocs")
            assert resp.status_code == 200

    def test_gallery_returns_items(self, project_root, monkeypatch):
        gateway_path = str(project_root / "gateway")
        if gateway_path not in sys.path:
            sys.path.insert(0, gateway_path)
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/v1/gallery/pocs")
            if resp.status_code == 200:
                data = resp.json()
                assert "items" in data
                assert len(data["items"]) >= 3


# ─── FRONTEND ───

class TestFrontendPhase2:

    def test_capacity_page_exists(self, project_root):
        assert (project_root / "frontend" / "src" / "pages" / "CapacityDashboard.tsx").exists()

    def test_gallery_page_exists(self, project_root):
        assert (project_root / "frontend" / "src" / "pages" / "PublishingHouse.tsx").exists()

    def test_capacity_route_exists(self, project_root):
        app_tsx = (project_root / "frontend" / "src" / "App.tsx").read_text()
        assert "/capacity" in app_tsx

    def test_gallery_route_exists(self, project_root):
        app_tsx = (project_root / "frontend" / "src" / "App.tsx").read_text()
        assert "/gallery" in app_tsx

    def test_nav_has_capacity(self, project_root):
        layout = (project_root / "frontend" / "src" / "components" / "AppLayout.tsx").read_text()
        assert "/capacity" in layout

    def test_nav_has_gallery(self, project_root):
        layout = (project_root / "frontend" / "src" / "components" / "AppLayout.tsx").read_text()
        assert "/gallery" in layout
