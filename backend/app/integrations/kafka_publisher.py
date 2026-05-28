"""Kafka event publisher — publishes lifecycle events to Kafka topics.

Graceful degradation: if Kafka is not configured or unreachable, events are
silently skipped. This runs alongside the existing webhook publisher, not
instead of it.

Bootstrap URL: KAFKA_BOOTSTRAP_SERVERS env var.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("launchpad.kafka")

KAFKA_BOOTSTRAP = os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS",
    "ecosystem-kafka-kafka-bootstrap.ecosystem-kafka.svc:9092",
)

TOPIC_MAP = {
    "session.requested": "launchpad-lifecycle",
    "session.provisioning": "launchpad-provisioning",
    "session.validating": "launchpad-lifecycle",
    "session.ready": "launchpad-lifecycle",
    "session.active": "launchpad-lifecycle",
    "session.resetting": "launchpad-lifecycle",
    "session.reclaimed": "launchpad-lifecycle",
    "session.expired": "launchpad-lifecycle",
    "session.failed": "launchpad-lifecycle",
    "session.validation_failed": "launchpad-lifecycle",
    "namespace.created": "launchpad-provisioning",
    "deployment.applied": "launchpad-provisioning",
    "route.created": "launchpad-provisioning",
}

AUDIT_TOPIC = "audit-trail"

_producer = None


def _get_producer():
    global _producer
    if _producer is not None:
        return _producer
    if not KAFKA_BOOTSTRAP:
        return None
    try:
        from kafka import KafkaProducer
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks=1,
            retries=2,
            request_timeout_ms=5000,
            max_block_ms=3000,
        )
        logger.info("Kafka producer connected to %s", KAFKA_BOOTSTRAP)
        return _producer
    except ImportError:
        logger.debug("kafka-python not installed — Kafka publishing disabled")
        return None
    except Exception as e:
        logger.debug("Kafka producer init failed (non-critical): %s", e)
        return None


def get_topic_for_event(event_type: str) -> str:
    return TOPIC_MAP.get(event_type, "launchpad-lifecycle")


def get_audit_topic() -> str:
    return AUDIT_TOPIC


def publish_to_kafka(topic: str, payload: dict, key: str = None) -> Optional[dict]:
    """Publish a message to a Kafka topic. Fails silently."""
    if not KAFKA_BOOTSTRAP:
        return {}
    producer = _get_producer()
    if not producer:
        return {}
    try:
        future = producer.send(topic, value=payload, key=key)
        producer.flush(timeout=3)
        return {"published": True, "topic": topic}
    except Exception as e:
        logger.debug("Kafka publish to %s failed (non-critical): %s", topic, e)
        return {}


def publish_event(event_type: str, payload: dict) -> None:
    """Publish an event to the appropriate topic + audit trail."""
    topic = get_topic_for_event(event_type)
    payload["_kafka_topic"] = topic
    payload["_published_at"] = datetime.now(timezone.utc).isoformat()
    publish_to_kafka(topic, payload, key=payload.get("session_id"))
    publish_to_kafka(AUDIT_TOPIC, payload, key=payload.get("session_id"))
