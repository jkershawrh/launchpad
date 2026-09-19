"""Approved event-manifest persistence without lifecycle side effects."""

from __future__ import annotations

from threading import Lock

from app.domain.events import EventManifestConflictError, EventRecord


class EventManifestStore:
    """Fail-closed event store with an in-memory development fallback.

    Event IDs are immutable. Creating an event never reserves capacity or
    provisions a workshop; those actions belong to a later, approval-gated
    orchestration step.
    """

    def __init__(self, db_store=None) -> None:
        self._records: dict[str, EventRecord] = {}
        self._db = db_store
        self._lock = Lock()

    def create(self, record: EventRecord) -> EventRecord:
        event_id = record.manifest.event_id
        with self._lock:
            if event_id in self._records:
                raise EventManifestConflictError(
                    f"Event manifest {event_id} already exists"
                )
            if self._db:
                self._db.create(record)
            self._records[event_id] = record
        return record

    def get(self, event_id: str) -> EventRecord | None:
        record = self._records.get(event_id)
        if record is None and self._db:
            record = self._db.get(event_id)
            if record:
                self._records[event_id] = record
        return record

    def list_all(self) -> list[EventRecord]:
        if self._db:
            for record in self._db.list_all():
                self._records[record.manifest.event_id] = record
        return list(self._records.values())
