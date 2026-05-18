#!/usr/bin/env python3
"""Kafka Event Producer — TDD Red Phase"""

import sys
import json
import pytest


@pytest.fixture(autouse=True)
def setup(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


class TestEventProducerModule:

    def test_importable(self):
        from overdrive.event_producer import get_event_producer
        assert get_event_producer is not None

    def test_stdout_producer_default(self, monkeypatch):
        monkeypatch.delenv("KAFKA_BROKERS", raising=False)
        from overdrive.event_producer import get_event_producer
        producer = get_event_producer()
        assert producer.__class__.__name__ == "StdoutEventProducer"

    def test_kafka_producer_when_env_set(self, monkeypatch):
        monkeypatch.setenv("KAFKA_BROKERS", "kafka:9092")
        from overdrive.event_producer import get_event_producer
        producer = get_event_producer()
        assert producer.__class__.__name__ == "KafkaEventProducer"


class TestStdoutEventProducer:

    def test_emit_returns_event(self):
        from overdrive.event_producer import StdoutEventProducer
        producer = StdoutEventProducer()
        event = producer.emit({
            "request_id": "test-001",
            "task_type": "classification",
            "lane": "eco",
            "latency_ms": 85.0,
        })
        assert event is not None
        assert event["request_id"] == "test-001"

    def test_emit_adds_timestamp(self):
        from overdrive.event_producer import StdoutEventProducer
        producer = StdoutEventProducer()
        event = producer.emit({"task_type": "classification"})
        assert "timestamp" in event

    def test_emit_adds_event_type(self):
        from overdrive.event_producer import StdoutEventProducer
        producer = StdoutEventProducer()
        event = producer.emit({"task_type": "classification"})
        assert event["event_type"] == "routing_decision"

    def test_get_events_returns_list(self):
        from overdrive.event_producer import StdoutEventProducer
        producer = StdoutEventProducer()
        producer.emit({"task_type": "classification"})
        producer.emit({"task_type": "embedding"})
        events = producer.get_events()
        assert isinstance(events, list)
        assert len(events) == 2


class TestKafkaEventProducer:

    def test_has_emit_method(self, monkeypatch):
        monkeypatch.setenv("KAFKA_BROKERS", "kafka:9092")
        from overdrive.event_producer import KafkaEventProducer
        producer = KafkaEventProducer(brokers="kafka:9092")
        assert hasattr(producer, "emit")

    def test_has_get_events_method(self, monkeypatch):
        monkeypatch.setenv("KAFKA_BROKERS", "kafka:9092")
        from overdrive.event_producer import KafkaEventProducer
        producer = KafkaEventProducer(brokers="kafka:9092")
        assert hasattr(producer, "get_events")

    def test_emit_without_broker_falls_back(self):
        from overdrive.event_producer import KafkaEventProducer
        producer = KafkaEventProducer(brokers="nonexistent:9092")
        event = producer.emit({"task_type": "classification"})
        assert event is not None


class TestBatchRunnerIntegration:

    def test_batch_runner_has_events(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        assert "events" in result
        assert isinstance(result["events"], list)
        assert len(result["events"]) > 0

    def test_events_have_routing_info(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42)
        for event in result["events"]:
            assert "task_type" in event
            assert "lane" in event
            assert "event_type" in event
