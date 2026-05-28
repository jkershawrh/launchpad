"""Kafka event publisher — TDD red/green.

Tests that lifecycle events publish to Kafka topics alongside existing webhook push.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestKafkaPublisherExists:
    """Kafka publisher module exists and is importable."""

    def test_kafka_publish_function_exists(self):
        from app.integrations.kafka_publisher import publish_to_kafka
        assert callable(publish_to_kafka)

    def test_kafka_publisher_has_bootstrap_config(self):
        from app.integrations.kafka_publisher import KAFKA_BOOTSTRAP
        assert isinstance(KAFKA_BOOTSTRAP, str)

    def test_kafka_publisher_has_topic_mapping(self):
        from app.integrations.kafka_publisher import TOPIC_MAP
        assert "session.active" in TOPIC_MAP or "lifecycle" in str(TOPIC_MAP)


class TestKafkaPublishEvent:
    """Events get published to the correct Kafka topic."""

    def test_lifecycle_event_goes_to_lifecycle_topic(self):
        from app.integrations.kafka_publisher import get_topic_for_event
        topic = get_topic_for_event("session.active")
        assert topic == "launchpad-lifecycle"

    def test_provisioning_event_goes_to_provisioning_topic(self):
        from app.integrations.kafka_publisher import get_topic_for_event
        topic = get_topic_for_event("session.provisioning")
        assert topic == "launchpad-provisioning"

    def test_all_events_also_go_to_audit_trail(self):
        from app.integrations.kafka_publisher import get_audit_topic
        assert get_audit_topic() == "audit-trail"


class TestKafkaGracefulDegradation:
    """Kafka publisher fails silently when Kafka is unavailable."""

    def test_publish_succeeds_when_no_bootstrap(self):
        from app.integrations.kafka_publisher import publish_to_kafka
        # Should not raise even if Kafka is not configured
        with patch("app.integrations.kafka_publisher.KAFKA_BOOTSTRAP", ""):
            result = publish_to_kafka("launchpad-lifecycle", {"test": True})
            assert result is None or result == {}

    def test_publish_succeeds_when_kafka_unreachable(self):
        from app.integrations.kafka_publisher import publish_to_kafka
        with patch("app.integrations.kafka_publisher.KAFKA_BOOTSTRAP", "unreachable:9092"):
            result = publish_to_kafka("launchpad-lifecycle", {"test": True})
            assert result is None or result == {}


class TestEventPublisherIntegration:
    """Existing event_publisher.py calls Kafka alongside webhook."""

    def test_publish_event_calls_kafka(self):
        from app.integrations import event_publisher
        with patch("app.integrations.event_publisher._push_kafka") as mock_kafka:
            event_publisher.publish_event(
                session_id="test-123",
                namespace="test-ns",
                status="active",
                lab_code="inference-overdrive",
            )
            mock_kafka.assert_called_once()
