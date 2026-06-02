"""E2E Integration tests — Launchpad ↔ StarGate.

These tests verify the integration contracts between products.
Run with live services or skip if endpoints unavailable.
"""

import os
import pytest

STARGATE_URL = os.environ.get("STARGATE_API_URL", "")

skip_no_stargate = pytest.mark.skipif(not STARGATE_URL, reason="STARGATE_API_URL not set")


class TestEventPublisher:
    def test_publish_event_noop_without_urls(self):
        from app.integrations.event_publisher import publish_event
        publish_event(
            session_id="test-sess",
            namespace="test-ns",
            status="ready",
            lab_code="inference-overdrive",
        )

    def test_publish_event_has_stargate_url_var(self):
        from app.integrations.event_publisher import STARGATE_API_URL
        assert STARGATE_API_URL is not None


class TestLLMAudit:
    def test_audit_log_records_call(self):
        from app.integrations.llm_audit import log_llm_call, get_llm_audit_log
        log_llm_call(
            model="granite-3-2-8b",
            prompt="test prompt",
            output="test output",
            latency_ms=142.5,
            trace_id="trace-001",
            caller="test",
        )
        log = get_llm_audit_log()
        assert len(log) >= 1
        last = log[-1]
        assert last["model"] == "granite-3-2-8b"
        assert last["latency_ms"] == 142.5
        assert last["trace_id"] == "trace-001"
        assert last["prompt_hash"]
