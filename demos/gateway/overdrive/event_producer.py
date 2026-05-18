"""Event producer — emits routing decision events to Kafka or stdout."""

import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StdoutEventProducer:
    """Logs events to stdout and stores in memory. Demo-friendly, no infra needed."""

    def __init__(self):
        self._events: list[dict] = []

    def emit(self, data: dict) -> dict:
        event = {
            "event_type": "routing_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        self._events.append(event)
        return event

    def get_events(self) -> list[dict]:
        return list(self._events)


class KafkaEventProducer:
    """Emits events to a Kafka topic. Falls back to in-memory if broker unavailable."""

    def __init__(self, brokers: str = "kafka:9092", topic: str = "routing-decisions"):
        self._brokers = brokers
        self._topic = topic
        self._events: list[dict] = []
        self._kafka_available = False
        try:
            from kafka import KafkaProducer
            self._producer = KafkaProducer(
                bootstrap_servers=brokers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                request_timeout_ms=2000,
                max_block_ms=2000,
            )
            self._kafka_available = True
        except Exception:
            self._producer = None

    def emit(self, data: dict) -> dict:
        event = {
            "event_type": "routing_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        self._events.append(event)
        if self._kafka_available and self._producer:
            try:
                self._producer.send(self._topic, value=event)
            except Exception:
                pass
        return event

    def get_events(self) -> list[dict]:
        return list(self._events)


def get_event_producer():
    brokers = os.getenv("KAFKA_BROKERS", "")
    if brokers:
        return KafkaEventProducer(brokers=brokers)
    return StdoutEventProducer()
