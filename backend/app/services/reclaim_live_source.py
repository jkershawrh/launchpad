"""Read-only PostgreSQL and Kubernetes source for reclaim inventory checks.

This source is deliberately not wired to an API, scheduler, or reclaim action.
The database roster is read under one repeatable-read, read-only transaction;
each cluster namespace roster is paginated and scanned twice for drift. A
balanced result is still not reclaim authorization or zero-residue evidence.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.events import EventCapacityReservation
from app.domain.models import LabSession, Workshop
from app.services.event_kubernetes_inventory_observer import _list_all
from app.services.reclaim_inventory_collector import (
    CollectionBatch,
    InventoryCollectionError,
    build_reclaim_inventory,
)
from app.storage.database import get_database_url


def _decode_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


@dataclass(frozen=True)
class DatabaseRoster:
    observed_at: datetime
    workshops: tuple[dict[str, Any], ...]
    sessions: tuple[dict[str, Any], ...]
    reservations: tuple[dict[str, Any], ...]


class PostgresReclaimRosterReader:
    """Project only reclaim identifiers from one durable read-only snapshot."""

    def __init__(
        self,
        connection_factory: Callable[[], Any] | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.connection_factory = connection_factory
        self.clock = clock

    def read(self) -> DatabaseRoster:
        connection = None
        try:
            if self.connection_factory is None:
                import psycopg2

                database_url = get_database_url()
                connection = (
                    psycopg2.connect(database_url, connect_timeout=5) if database_url else None
                )
            else:
                connection = self.connection_factory()
            if connection is None:
                raise InventoryCollectionError("durable read-only roster unavailable")
            connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT data FROM workshops WHERE status IN ('ready', 'active') "
                    "ORDER BY workshop_id"
                )
                workshops = [
                    Workshop.model_validate(_decode_json(row[0])) for row in cursor.fetchall()
                ]
                session_ids = sorted({sid for item in workshops for sid in item.session_ids})
                sessions: list[LabSession] = []
                if session_ids:
                    cursor.execute(
                        "SELECT data FROM lab_sessions WHERE session_id = ANY(%s) "
                        "ORDER BY session_id",
                        (session_ids,),
                    )
                    sessions = [
                        LabSession.model_validate(_decode_json(row[0])) for row in cursor.fetchall()
                    ]
                reservation_ids = sorted(
                    {
                        item.metadata["event_reservation_id"]
                        for item in workshops
                        if item.metadata.get("event_reservation_id")
                    }
                )
                reservations: list[EventCapacityReservation] = []
                if reservation_ids:
                    cursor.execute(
                        "SELECT data FROM event_capacity_reservations "
                        "WHERE reservation_id = ANY(%s) ORDER BY reservation_id",
                        (reservation_ids,),
                    )
                    reservations = [
                        EventCapacityReservation.model_validate(_decode_json(row[0]))
                        for row in cursor.fetchall()
                    ]

            if len(sessions) != len(session_ids) or {s.session_id for s in sessions} != set(
                session_ids
            ):
                raise InventoryCollectionError("persisted workshop session roster is incomplete")
            if len(reservations) != len(reservation_ids) or {
                item.reservation_id for item in reservations
            } != set(reservation_ids):
                raise InventoryCollectionError(
                    "persisted workshop reservation roster is incomplete"
                )
            seat_numbers: dict[str, dict[str, int]] = {}
            for workshop in workshops:
                if not workshop.cluster_ref or len(workshop.seats) != workshop.num_users:
                    raise InventoryCollectionError("persisted workshop seat roster is incomplete")
                seats = {
                    seat.session_id: seat.seat_number for seat in workshop.seats if seat.session_id
                }
                if set(seats) != set(workshop.session_ids) or len(seats) != len(workshop.seats):
                    raise InventoryCollectionError(
                        "persisted workshop seat ownership is incomplete"
                    )
                seat_numbers[workshop.workshop_id] = seats
            session_by_id = {session.session_id: session for session in sessions}
            projected_sessions = []
            for workshop in workshops:
                for session_id in workshop.session_ids:
                    session = session_by_id[session_id]
                    if not session.namespace or not session.cluster_ref:
                        raise InventoryCollectionError("persisted session placement is incomplete")
                    projected_sessions.append(
                        {
                            "session_id": session_id,
                            "workshop_id": workshop.workshop_id,
                            "cluster_ref": session.cluster_ref,
                            "namespace": session.namespace,
                            "seat_number": seat_numbers[workshop.workshop_id][session_id],
                            "state": session.status.value,
                        }
                    )
            observed_at = self.clock()
            if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
                raise InventoryCollectionError("roster observation time is invalid")
            return DatabaseRoster(
                observed_at=observed_at,
                workshops=tuple(
                    {
                        "workshop_id": item.workshop_id,
                        "cluster_ref": item.cluster_ref,
                        "seat_count": item.num_users,
                        "reservation_id": item.metadata.get("event_reservation_id"),
                        "state": item.status.value,
                    }
                    for item in workshops
                ),
                sessions=tuple(projected_sessions),
                reservations=tuple(
                    {
                        "reservation_id": item.reservation_id,
                        "workshop_id": item.workshop_id,
                        "cluster_ref": item.cluster_ref,
                        "seat_count": item.resources.seats,
                        "state": item.status,
                    }
                    for item in reservations
                ),
            )
        except InventoryCollectionError:
            raise
        except Exception:  # noqa: BLE001 - database failures can contain credentials
            raise InventoryCollectionError("durable read-only roster unavailable") from None
        finally:
            if connection is not None:
                cleanup_failed = False
                try:
                    connection.rollback()
                except Exception:  # noqa: BLE001 - do not expose driver diagnostics
                    cleanup_failed = True
                try:
                    connection.close()
                except Exception:  # noqa: BLE001 - do not expose driver diagnostics
                    cleanup_failed = True
                if cleanup_failed:
                    raise InventoryCollectionError(
                        "durable read-only roster cleanup failed"
                    ) from None


class LiveReclaimInventorySource:
    """Combine one persisted roster with double-scanned target namespaces."""

    def __init__(
        self,
        reader: PostgresReclaimRosterReader,
        registry: Any,
        client_factory: Any,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.roster = reader.read()
        self.cluster_refs = tuple(target.cluster_id for target in registry.list_all())
        if not self.cluster_refs or len(set(self.cluster_refs)) != len(self.cluster_refs):
            raise InventoryCollectionError("registered cluster roster is invalid")
        self.client_factory = client_factory
        self.clock = clock

    def list_cluster_refs(self) -> CollectionBatch:
        return CollectionBatch(
            [{"cluster_ref": cluster} for cluster in self.cluster_refs],
            True,
            self.roster.observed_at,
        )

    def list_retained_workshops(self) -> CollectionBatch:
        return CollectionBatch(list(self.roster.workshops), True, self.roster.observed_at)

    def list_sessions(self, workshop_ids: frozenset[str]) -> CollectionBatch:
        self._check_scope(workshop_ids)
        return CollectionBatch(list(self.roster.sessions), True, self.roster.observed_at)

    def list_reservations(self, workshop_ids: frozenset[str]) -> CollectionBatch:
        self._check_scope(workshop_ids)
        return CollectionBatch(list(self.roster.reservations), True, self.roster.observed_at)

    def _check_scope(self, workshop_ids: frozenset[str]) -> None:
        if workshop_ids != frozenset(item["workshop_id"] for item in self.roster.workshops):
            raise InventoryCollectionError("persisted workshop scope changed")

    def _scan_namespaces(self, core: Any, cluster_ref: str) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        workshop_ids = {item["workshop_id"] for item in self.roster.workshops}
        session_ids = {item["session_id"] for item in self.roster.sessions}
        for namespace in _list_all(core.list_namespace, "namespace"):
            metadata = getattr(namespace, "metadata", None)
            labels = getattr(metadata, "labels", None) or {}
            if not isinstance(labels, dict):
                raise InventoryCollectionError("namespace labels are invalid")
            workshop_id = labels.get("launchpad.redhat.com/workshop-id", "")
            session_id = labels.get("launchpad.redhat.com/session-id", "")
            if workshop_id not in workshop_ids and session_id not in session_ids:
                continue
            if labels.get("launchpad.redhat.com/cluster-id") != cluster_ref:
                raise InventoryCollectionError("namespace cluster label differs from target")
            name = getattr(metadata, "name", None)
            if not isinstance(name, str) or not name:
                raise InventoryCollectionError("namespace identity is incomplete")
            result.append(
                {
                    "namespace": name,
                    "cluster_ref": cluster_ref,
                    "workshop_id": workshop_id,
                    "session_id": session_id,
                }
            )
        return sorted(result, key=lambda item: item["namespace"])

    def list_managed_namespaces(self, cluster_ref: str) -> CollectionBatch:
        if cluster_ref not in self.cluster_refs:
            raise InventoryCollectionError("namespace target is not registered")
        try:
            core = self.client_factory.clients(cluster_ref, allow_disabled=True).core
            observed_at = self.clock()
            first = self._scan_namespaces(core, cluster_ref)
            second = self._scan_namespaces(core, cluster_ref)
            if first != second:
                raise InventoryCollectionError("namespace inventory changed during observation")
            return CollectionBatch(first, True, observed_at)
        except InventoryCollectionError:
            raise
        except Exception:  # noqa: BLE001 - cluster errors may contain private endpoint details
            raise InventoryCollectionError("authenticated namespace scan unavailable") from None


def main(source: Any = None, *, now: datetime | None = None) -> int:
    """Emit only a complete checked snapshot; never request reclaim."""
    try:
        if source is None:
            from app.adapters.openshift.client_factory import ClusterClientFactory
            from app.services.cluster_registry import ClusterRegistry

            registry = ClusterRegistry.from_file()
            source = LiveReclaimInventorySource(
                PostgresReclaimRosterReader(), registry, ClusterClientFactory(registry)
            )
        payload = build_reclaim_inventory(source, now=now)
    except Exception:  # noqa: BLE001 - no secret-bearing provider failures in operator output
        print("read-only reclaim inventory blocked", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
