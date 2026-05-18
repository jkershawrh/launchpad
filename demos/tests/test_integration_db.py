#!/usr/bin/env python3
"""
Integration Tests — Live PostgreSQL

These tests run against a real PostgreSQL instance.
They validate that SQL actually works, migrations apply,
data persists, queries filter correctly, and the full
request→persist→query cycle functions end-to-end.

Requires: DATABASE_URL env var pointing to a running PostgreSQL.
Skip gracefully if not available.

Start PostgreSQL for testing:
  podman run -d --name demo-postgres -p 5433:5432 \
    -e POSTGRES_USER=gateway -e POSTGRES_PASSWORD=testpass \
    -e POSTGRES_DB=inference_platform \
    docker.io/library/postgres:15-alpine

Run:
  DATABASE_URL=postgresql://gateway:testpass@localhost:5433/inference_platform \
    pytest tests/test_integration_db.py -v
"""

import os
import sys
import asyncio
import pytest
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping integration tests (need live PostgreSQL)"
)

# Add gateway to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "gateway"))


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def db_module():
    import db
    db.DATABASE_URL = DATABASE_URL
    return db


@pytest.fixture(scope="module", autouse=True)
def setup_db(event_loop, db_module):
    """Connect to DB, run migrations, yield, then clean up"""
    connected = event_loop.run_until_complete(db_module.connect())
    assert connected, "Failed to connect to PostgreSQL"
    event_loop.run_until_complete(db_module.run_migrations())
    yield
    # Clean up test data
    async def cleanup():
        if db_module._pool:
            async with db_module._pool.acquire() as conn:
                await conn.execute("DELETE FROM audit_log")
                await conn.execute("DELETE FROM governance_decisions")
                await conn.execute("DELETE FROM inference_requests")
                await conn.execute("DELETE FROM routing_rules")
                await conn.execute("DELETE FROM backends")
            await db_module.disconnect()
    event_loop.run_until_complete(cleanup())


class TestMigrations:
    """Test that migrations create the schema correctly"""

    def test_inference_requests_table_exists(self, event_loop, db_module):
        async def check():
            async with db_module._pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'inference_requests')"
                )
                return exists
        assert event_loop.run_until_complete(check()) is True

    def test_governance_decisions_table_exists(self, event_loop, db_module):
        async def check():
            async with db_module._pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'governance_decisions')"
                )
        assert event_loop.run_until_complete(check()) is True

    def test_backends_table_exists(self, event_loop, db_module):
        async def check():
            async with db_module._pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'backends')"
                )
        assert event_loop.run_until_complete(check()) is True

    def test_migrations_are_idempotent(self, event_loop, db_module):
        """Running migrations twice should not error"""
        event_loop.run_until_complete(db_module.run_migrations())


class TestInsertRequest:
    """Test inserting and retrieving inference requests"""

    def test_insert_returns_uuid(self, event_loop, db_module):
        async def insert():
            return await db_module.insert_request(
                task="completion", backend="vllm-cpu", accelerator="xeon6",
                status="success", latency_ms=150.5, cost_estimate=0.002,
                reason="Small model fits CPU", model="TinyLlama", model_size_b=1.1
            )
        request_id = event_loop.run_until_complete(insert())
        assert request_id is not None
        assert len(request_id) == 36  # UUID format

    def test_inserted_request_retrievable_by_id(self, event_loop, db_module):
        async def test():
            req_id = await db_module.insert_request(
                task="embeddings", backend="openvino-cpu", accelerator="xeon6",
                status="success", latency_ms=4.2, cost_estimate=0.001,
                reason="AMX-accelerated"
            )
            row = await db_module.get_request_by_id(req_id)
            assert row is not None
            assert row['task'] == 'embeddings'
            assert row['backend'] == 'openvino-cpu'
            assert row['status'] == 'success'
            assert abs(row['latency_ms'] - 4.2) < 0.01
        event_loop.run_until_complete(test())

    def test_get_request_by_invalid_id_returns_none(self, event_loop, db_module):
        async def test():
            return await db_module.get_request_by_id("00000000-0000-0000-0000-000000000000")
        assert event_loop.run_until_complete(test()) is None

    def test_insert_error_request(self, event_loop, db_module):
        async def insert():
            return await db_module.insert_request(
                task="completion", backend="vllm-gaudi", accelerator="gaudi",
                status="error", latency_ms=0, cost_estimate=0,
                reason="Backend unreachable", error_detail="Connection refused"
            )
        req_id = event_loop.run_until_complete(insert())
        assert req_id is not None


class TestQueryFiltering:
    """Test that query filters work correctly"""

    def test_filter_by_task(self, event_loop, db_module):
        async def test():
            await db_module.insert_request(
                task="classification", backend="openvino-cpu", accelerator="xeon6",
                status="success", latency_ms=3.0, cost_estimate=0.001, reason="test"
            )
            rows = await db_module.get_requests(task="classification")
            assert len(rows) > 0
            assert all(r['task'] == 'classification' for r in rows)
        event_loop.run_until_complete(test())

    def test_filter_by_backend(self, event_loop, db_module):
        async def test():
            rows = await db_module.get_requests(backend="openvino-cpu")
            assert len(rows) > 0
            assert all(r['backend'] == 'openvino-cpu' for r in rows)
        event_loop.run_until_complete(test())

    def test_filter_by_status(self, event_loop, db_module):
        async def test():
            rows = await db_module.get_requests(status="error")
            assert len(rows) > 0
            assert all(r['status'] == 'error' for r in rows)
        event_loop.run_until_complete(test())

    def test_combined_filters(self, event_loop, db_module):
        async def test():
            rows = await db_module.get_requests(task="embeddings", backend="openvino-cpu", status="success")
            assert all(r['task'] == 'embeddings' and r['backend'] == 'openvino-cpu' for r in rows)
        event_loop.run_until_complete(test())

    def test_pagination_limit(self, event_loop, db_module):
        async def test():
            rows = await db_module.get_requests(limit=2)
            assert len(rows) <= 2
        event_loop.run_until_complete(test())

    def test_pagination_offset(self, event_loop, db_module):
        async def test():
            all_rows = await db_module.get_requests(limit=100)
            offset_rows = await db_module.get_requests(limit=100, offset=1)
            if len(all_rows) > 1:
                assert len(offset_rows) == len(all_rows) - 1
        event_loop.run_until_complete(test())

    def test_ordering_by_created_at_desc(self, event_loop, db_module):
        async def test():
            rows = await db_module.get_requests(limit=10)
            if len(rows) >= 2:
                assert rows[0]['created_at'] >= rows[1]['created_at']
        event_loop.run_until_complete(test())


class TestGovernanceDecisions:
    """Test governance decision persistence"""

    def test_insert_governance_decision(self, event_loop, db_module):
        async def test():
            req_id = await db_module.insert_request(
                task="completion", backend="vllm-gaudi", accelerator="gaudi",
                status="success", latency_ms=1200, cost_estimate=0.008,
                reason="Large model needs Gaudi"
            )
            dec_id = await db_module.insert_governance_decision(
                request_id=req_id, source="governed-agent",
                intent="restart_pod", risk_score=0.45, risk_level="medium",
                decision="allow_with_audit",
                reason="Risk score within audit range",
                evidence={"request": "restart pods", "amplifiers": []}
            )
            assert dec_id is not None
            return dec_id
        event_loop.run_until_complete(test())

    def test_get_decision_by_id(self, event_loop, db_module):
        async def test():
            req_id = await db_module.insert_request(
                task="classification", backend="openvino-cpu", accelerator="xeon6",
                status="success", latency_ms=3, cost_estimate=0.001, reason="test"
            )
            dec_id = await db_module.insert_governance_decision(
                request_id=req_id, source="aiops-copilot",
                intent="scale_deployment", risk_score=0.3, risk_level="low",
                decision="auto_approved", reason="Low risk",
                evidence={"alert": "high latency"}
            )
            row = await db_module.get_decision_by_id(dec_id)
            assert row is not None
            assert row['decision'] == 'auto_approved'
            assert row['source'] == 'aiops-copilot'
            assert row['intent'] == 'scale_deployment'
        event_loop.run_until_complete(test())

    def test_filter_decisions_by_decision_type(self, event_loop, db_module):
        async def test():
            rows = await db_module.get_decisions(decision="auto_approved")
            assert all(r['decision'] == 'auto_approved' for r in rows)
        event_loop.run_until_complete(test())

    def test_filter_decisions_by_source(self, event_loop, db_module):
        async def test():
            rows = await db_module.get_decisions(source="aiops-copilot")
            assert all(r['source'] == 'aiops-copilot' for r in rows)
        event_loop.run_until_complete(test())

    def test_evidence_stored_as_jsonb(self, event_loop, db_module):
        async def test():
            req_id = await db_module.insert_request(
                task="completion", backend="vllm-cpu", accelerator="xeon6",
                status="success", latency_ms=500, cost_estimate=0.002, reason="test"
            )
            evidence = {"intent": "patch_deployment", "risk_amplifiers": ["production"], "timestamp": "2026-05-04T12:00:00Z"}
            dec_id = await db_module.insert_governance_decision(
                request_id=req_id, source="governed-agent",
                intent="patch_deployment", risk_score=0.9, risk_level="high",
                decision="escalate", reason="High risk",
                evidence=evidence
            )
            row = await db_module.get_decision_by_id(dec_id)
            assert row is not None
            import json
            stored = json.loads(row['evidence']) if isinstance(row['evidence'], str) else row['evidence']
            assert stored['intent'] == 'patch_deployment'
            assert 'production' in stored['risk_amplifiers']
        event_loop.run_until_complete(test())


class TestApprovalWorkflow:
    """Test the governance approval workflow"""

    def test_approve_decision(self, event_loop, db_module):
        async def test():
            req_id = await db_module.insert_request(
                task="completion", backend="vllm-gaudi", accelerator="gaudi",
                status="success", latency_ms=1000, cost_estimate=0.008, reason="test"
            )
            dec_id = await db_module.insert_governance_decision(
                request_id=req_id, source="governed-agent",
                intent="restart_node", risk_score=0.85, risk_level="high",
                decision="escalate", reason="Needs human approval",
                evidence={}
            )
            success = await db_module.approve_decision(dec_id, "jonathan.kershaw")
            assert success is True

            row = await db_module.get_decision_by_id(dec_id)
            assert row['approved_by'] == 'jonathan.kershaw'
            assert row['approved_at'] is not None
        event_loop.run_until_complete(test())

    def test_approve_nonexistent_returns_false(self, event_loop, db_module):
        async def test():
            return await db_module.approve_decision("00000000-0000-0000-0000-000000000000", "admin")
        assert event_loop.run_until_complete(test()) is False


class TestConfigSeeding:
    """Test seeding from config.yaml"""

    def test_seed_from_config(self, event_loop, db_module):
        async def test():
            # Clear backends to test seeding into empty table
            async with db_module._pool.acquire() as conn:
                await conn.execute("DELETE FROM routing_rules")
                await conn.execute("DELETE FROM backends")

            config = {
                "backends": [
                    {"name": "test-cpu", "url": "http://test:8000", "accelerator": "xeon6",
                     "capabilities": ["completion"], "cost_per_1k_tokens": 0.001},
                ],
                "routes": [
                    {"task": "completion", "backend": "test-cpu", "reason": "test route"},
                ]
            }
            await db_module.seed_from_config(config)

            backends = await db_module.get_backends_from_db()
            names = [b['name'] for b in backends]
            assert 'test-cpu' in names

            rules = await db_module.get_routing_rules()
            assert len(rules) > 0
        event_loop.run_until_complete(test())

    def test_seed_idempotent(self, event_loop, db_module):
        """Seeding twice should not duplicate data — second call skips"""
        async def test():
            # Table already has data from test above
            config = {"backends": [
                {"name": "test-cpu-2", "url": "http://test:8001", "accelerator": "xeon6",
                 "capabilities": ["completion"]},
            ], "routes": []}
            await db_module.seed_from_config(config)
            # Should skip because backends table is not empty
            backends = await db_module.get_backends_from_db()
            names = [b['name'] for b in backends]
            assert 'test-cpu-2' not in names, "Second seed should be skipped when table is non-empty"
        event_loop.run_until_complete(test())


class TestAuditLog:
    """Test audit log entries"""

    def test_seed_creates_audit_entries(self, event_loop, db_module):
        async def test():
            async with db_module._pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM audit_log WHERE entity_type = 'backends'"
                )
                return count
        count = event_loop.run_until_complete(test())
        assert count > 0, "Seeding should create audit log entries"

    def test_approval_creates_audit_entry(self, event_loop, db_module):
        async def test():
            async with db_module._pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM audit_log WHERE action = 'approve'"
                )
                return count
        count = event_loop.run_until_complete(test())
        assert count > 0, "Approval should create audit log entry"


class TestAnalyticsQueries:
    """Test that analytics SQL actually executes without error"""

    def test_cost_summary_executes(self, event_loop, db_module):
        result = event_loop.run_until_complete(db_module.get_cost_summary(days=30))
        assert isinstance(result, list)

    def test_routing_distribution_executes(self, event_loop, db_module):
        result = event_loop.run_until_complete(db_module.get_routing_distribution(days=7))
        assert isinstance(result, list)

    def test_latency_percentiles_executes(self, event_loop, db_module):
        result = event_loop.run_until_complete(db_module.get_latency_percentiles(days=7))
        assert isinstance(result, list)

    def test_cost_by_task_executes(self, event_loop, db_module):
        result = event_loop.run_until_complete(db_module.get_cost_by_task(days=30))
        assert isinstance(result, list)

    def test_governance_summary_executes(self, event_loop, db_module):
        result = event_loop.run_until_complete(db_module.get_governance_summary(days=30))
        assert isinstance(result, list)

    def test_routing_distribution_has_data(self, event_loop, db_module):
        result = event_loop.run_until_complete(db_module.get_routing_distribution(days=1))
        assert len(result) > 0, "Should have routing distribution from inserted test data"
        for row in result:
            assert 'backend' in row
            assert 'count' in row
            assert 'pct' in row
