#!/usr/bin/env python3
"""
Tests for Database Schema, Module, and Behavior (Stage 8)

Tests are organized in two tiers:
- Structural: validates files, SQL syntax, module API (always runs)
- Behavioral: tests db functions work correctly without DB (graceful degradation)
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
def migration_sql(migrations_dir) -> str:
    sql_file = migrations_dir / "001_initial_schema.sql"
    if not sql_file.exists():
        pytest.skip("Migration file not created yet")
    return sql_file.read_text()


@pytest.fixture
def db_module(project_root):
    """Import the db module with gateway on sys.path, cleaning up afterward."""
    gateway_path = str(project_root / "gateway")
    sys.path.insert(0, gateway_path)
    import db
    importlib.reload(db)
    yield db
    sys.path.remove(gateway_path)


# --- Structural Tests (Schema validation) ---

class TestMigrationFiles:
    """Test migration file structure"""

    def test_migrations_directory_exists(self, migrations_dir):
        assert migrations_dir.exists()

    def test_initial_migration_exists(self, migrations_dir):
        assert (migrations_dir / "001_initial_schema.sql").exists()

    def test_migration_is_valid_sql(self, migration_sql):
        assert len(migration_sql) > 100
        assert 'CREATE TABLE' in migration_sql.upper()


class TestSchemaIdempotency:
    """Test that schema is safe to re-run"""

    def test_uses_if_not_exists_for_tables(self, migration_sql):
        create_tables = re.findall(r'CREATE TABLE\b.*', migration_sql, re.IGNORECASE)
        for stmt in create_tables:
            assert 'IF NOT EXISTS' in stmt.upper(), \
                f"CREATE TABLE should use IF NOT EXISTS: {stmt[:60]}"

    def test_uses_if_not_exists_for_indexes(self, migration_sql):
        create_indexes = re.findall(r'CREATE INDEX\b.*', migration_sql, re.IGNORECASE)
        for stmt in create_indexes:
            assert 'IF NOT EXISTS' in stmt.upper(), \
                f"CREATE INDEX should use IF NOT EXISTS: {stmt[:60]}"


class TestSchemaStructure:
    """Test that schema defines all required tables with correct columns"""

    def test_inference_requests_table(self, migration_sql):
        assert 'inference_requests' in migration_sql

    def test_governance_decisions_table(self, migration_sql):
        assert 'governance_decisions' in migration_sql

    def test_backends_table(self, migration_sql):
        assert 'backends' in migration_sql

    def test_routing_rules_table(self, migration_sql):
        assert 'routing_rules' in migration_sql

    def test_audit_log_table(self, migration_sql):
        assert 'audit_log' in migration_sql

    def test_governance_references_requests(self, migration_sql):
        assert re.search(r'REFERENCES\s+inference_requests', migration_sql, re.IGNORECASE)

    def test_routing_rules_references_backends(self, migration_sql):
        assert re.search(r'REFERENCES\s+backends', migration_sql, re.IGNORECASE)

    def test_backends_name_is_unique(self, migration_sql):
        assert re.search(r'name\s+VARCHAR.*UNIQUE', migration_sql, re.IGNORECASE)

    def test_evidence_column_is_jsonb(self, migration_sql):
        assert re.search(r'evidence\s+JSONB', migration_sql, re.IGNORECASE)

    def test_capabilities_is_text_array(self, migration_sql):
        assert re.search(r'capabilities\s+TEXT\s*\[\]', migration_sql, re.IGNORECASE)

    def test_has_composite_index(self, migration_sql):
        assert re.search(r'idx_requests_task_backend_created', migration_sql, re.IGNORECASE), \
            "Should have composite index on (task, backend, created_at)"


class TestSchemaSQL:
    """Test SQL uses correct PostgreSQL patterns"""

    def test_uses_make_interval_not_string_interpolation(self, gateway_dir):
        """db.py should use make_interval() not INTERVAL '%s days' for parameterized queries"""
        db_file = gateway_dir / "db.py"
        if not db_file.exists():
            pytest.skip("db.py not created yet")
        content = db_file.read_text()
        assert "INTERVAL '%s" not in content, \
            "Should use make_interval(days => $N), not INTERVAL '%s days' (SQL injection risk)"
        assert 'make_interval' in content, \
            "Should use make_interval() for parameterized interval queries"

    def test_no_direct_pool_access_in_api(self, gateway_dir):
        """api.py should not access db._pool directly"""
        api_file = gateway_dir / "api.py"
        if not api_file.exists():
            pytest.skip("api.py not created yet")
        content = api_file.read_text()
        assert 'db._pool' not in content, \
            "API should use db module functions, not access _pool directly"


# --- Behavioral Tests (db module functions without DB) ---

class TestDbModule:
    """Test db.py module structure and API"""

    def test_db_module_exists(self, gateway_dir):
        assert (gateway_dir / "db.py").exists()

    def test_db_module_compiles(self, gateway_dir):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(gateway_dir / "db.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_db_exports_required_functions(self, gateway_dir):
        content = (gateway_dir / "db.py").read_text()
        required = [
            'async def connect',
            'async def disconnect',
            'async def is_connected',
            'async def run_migrations',
            'async def seed_from_config',
            'async def insert_request',
            'async def insert_governance_decision',
            'async def get_request_by_id',
            'async def get_decision_by_id',
            'async def get_requests',
            'async def get_decisions',
            'async def get_backends_from_db',
            'async def get_routing_rules',
            'async def get_cost_summary',
            'async def get_routing_distribution',
            'async def get_latency_percentiles',
            'async def get_cost_by_task',
            'async def get_governance_summary',
            'async def approve_decision',
        ]
        for func in required:
            assert func in content, f"Missing function: {func}"


class TestDbGracefulDegradation:
    """Test that db functions return safely when no database is connected"""

    def test_is_connected_returns_false(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(db_module.is_connected())
        assert result is False

    def test_insert_request_returns_none(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.insert_request(
                task="completion", backend="vllm-cpu", accelerator="xeon6",
                status="success", latency_ms=100.0, cost_estimate=0.002,
                reason="test"
            )
        )
        assert result is None

    def test_get_requests_returns_empty(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(db_module.get_requests())
        assert result == []

    def test_get_decisions_returns_empty(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(db_module.get_decisions())
        assert result == []

    def test_get_request_by_id_returns_none(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.get_request_by_id("00000000-0000-0000-0000-000000000000")
        )
        assert result is None

    def test_get_backends_returns_empty(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(db_module.get_backends_from_db())
        assert result == []

    def test_get_routing_rules_returns_empty(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(db_module.get_routing_rules())
        assert result == []

    def test_approve_decision_returns_false(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(
            db_module.approve_decision("00000000-0000-0000-0000-000000000000", "admin")
        )
        assert result is False

    def test_get_cost_summary_returns_empty(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(db_module.get_cost_summary())
        assert result == []

    def test_get_governance_summary_returns_empty(self, db_module):
        result = asyncio.get_event_loop().run_until_complete(db_module.get_governance_summary())
        assert result == []


class TestDbHardening:
    """Database module hardening tests"""

    def test_migration_tracking_table(self, project_root):
        """db.py should use applied_migrations table for tracking"""
        content = (project_root / "gateway" / "db.py").read_text()
        assert 'applied_migrations' in content, \
            "Should use applied_migrations table for migration tracking"

    def test_is_connected_sends_select(self, project_root):
        """is_connected() should execute SELECT 1, not just check _pool"""
        content = (project_root / "gateway" / "db.py").read_text()
        assert 'SELECT 1' in content or 'select 1' in content, \
            "is_connected should test pool with SELECT 1"

    def test_seed_validates_backend_id(self, project_root):
        """seed_from_config should validate backend_id is not None"""
        content = (project_root / "gateway" / "db.py").read_text()
        assert 'backend_id is None' in content or 'not backend_id' in content, \
            "Should validate backend_id before inserting routing rules"

    def test_audit_uses_connection_param(self, project_root):
        """_audit should accept conn parameter"""
        content = (project_root / "gateway" / "db.py").read_text()
        import re
        audit_sig = re.search(r'async def _audit\((.*?)\)', content)
        assert audit_sig, "_audit function should exist"
        assert 'conn' in audit_sig.group(1), \
            "_audit should accept conn parameter"

    def test_no_redundant_except(self, project_root):
        """Should not have except (ValueError, Exception) pattern"""
        content = (project_root / "gateway" / "db.py").read_text()
        assert '(ValueError, Exception)' not in content, \
            "Use except Exception, not (ValueError, Exception)"

    def test_has_status_created_composite_index(self, project_root):
        """Migration should have composite index on (status, created_at)"""
        sql_file = project_root / "gateway" / "migrations" / "001_initial_schema.sql"
        content = sql_file.read_text()
        assert 'status, created_at' in content or 'status,created_at' in content, \
            "Should have composite index on (status, created_at)"

    def test_has_updated_at_trigger(self, project_root):
        """Migration should have updated_at trigger"""
        sql_file = project_root / "gateway" / "migrations" / "001_initial_schema.sql"
        content = sql_file.read_text()
        assert 'trigger' in content.lower() and 'updated_at' in content, \
            "Should have updated_at trigger on backends"

    def test_has_query_timeout(self, project_root):
        """Pool should have statement_timeout"""
        content = (project_root / "gateway" / "db.py").read_text()
        assert 'statement_timeout' in content, \
            "Pool should configure statement_timeout"
