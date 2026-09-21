"""Fail-closed, local-only bridge from persisted rosters to in-flight accounting.

The source must provide one complete, consistent database observation. Reading
separate workshop/session stores without a transaction is not an implementation
of this protocol. This module does not fetch credentials or enable admission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.events import EventCapacityReservation
from app.domain.models import LabSession, Workshop
from app.services.event_inflight_capacity_collector import InflightCollectionBlocked


@dataclass(frozen=True)
class PersistedRosterSnapshot:
    observed_at: datetime
    workshops: tuple[Workshop, ...]
    sessions: tuple[LabSession, ...]
    workshops_complete: bool = True
    sessions_complete: bool = True


class PersistedRosterSource(Protocol):
    def observe(self) -> PersistedRosterSnapshot:
        """Read a complete, transactionally consistent persisted roster."""


def _identity(value: str | None) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def collect_persisted_seat_evidence(
    source: PersistedRosterSource,
    reservations: list[EventCapacityReservation],
    *,
    now: datetime,
) -> dict[str, set[str]]:
    """Return exact consumed-workshop seat IDs for collect_inflight_capacity.

    Entity update timestamps are *not* freshness markers: a ready seat may be
    unchanged for hours. Freshness belongs to the authoritative observation.
    """

    if now.tzinfo is None:
        raise InflightCollectionBlocked("roster collection time requires timezone")
    try:
        snapshot = source.observe()
    except Exception as exc:
        raise InflightCollectionBlocked("persisted roster unavailable") from exc
    if not isinstance(snapshot, PersistedRosterSnapshot):
        raise InflightCollectionBlocked("persisted roster source returned invalid evidence")
    if snapshot.workshops_complete is not True or snapshot.sessions_complete is not True:
        raise InflightCollectionBlocked("persisted workshop/session roster incomplete")
    observed_at = snapshot.observed_at
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        raise InflightCollectionBlocked("persisted roster time requires timezone")
    age = (now - observed_at).total_seconds()
    if age > 120 or age < -30:
        raise InflightCollectionBlocked("persisted roster is stale or future-dated")

    workshops: dict[str, Workshop] = {}
    for workshop in snapshot.workshops:
        if not isinstance(workshop, Workshop) or not _identity(workshop.workshop_id):
            raise InflightCollectionBlocked("invalid persisted workshop")
        if workshop.workshop_id in workshops:
            raise InflightCollectionBlocked("duplicate persisted workshop")
        workshops[workshop.workshop_id] = workshop
    sessions: dict[str, LabSession] = {}
    for session in snapshot.sessions:
        if not isinstance(session, LabSession) or not _identity(session.session_id):
            raise InflightCollectionBlocked("invalid persisted session")
        if session.session_id in sessions:
            raise InflightCollectionBlocked("duplicate persisted session")
        sessions[session.session_id] = session

    result: dict[str, set[str]] = {}
    used_seats: set[str] = set()
    used_sessions: set[str] = set()
    for reservation in reservations:
        if not isinstance(reservation, EventCapacityReservation):
            raise InflightCollectionBlocked("invalid persisted reservation evidence")
        if reservation.status != "consumed":
            continue
        workshop_id = reservation.workshop_id
        if not workshop_id or workshop_id in result:
            raise InflightCollectionBlocked("duplicate or missing reservation workshop")
        if reservation.consumed_at is None or observed_at < reservation.consumed_at:
            raise InflightCollectionBlocked("roster predates reservation consumption")
        workshop = workshops.get(workshop_id)
        if workshop is None:
            raise InflightCollectionBlocked("persisted workshop is missing")
        if (
            workshop.cluster_ref != reservation.cluster_ref
            or workshop.catalog_item_id != reservation.catalog_id
            or workshop.num_users != reservation.resources.seats
            or workshop.num_users != len(workshop.seats)
        ):
            raise InflightCollectionBlocked("persisted workshop identity or size mismatch")
        seat_ids: set[str] = set()
        seat_numbers: set[int] = set()
        linked_sessions: set[str] = set()
        for seat in workshop.seats:
            if seat.workshop_id != workshop_id or not _identity(seat.seat_id):
                raise InflightCollectionBlocked("persisted seat workshop identity mismatch")
            if seat.seat_id in seat_ids or seat.seat_id in used_seats:
                raise InflightCollectionBlocked("duplicate persisted seat identity")
            if seat.seat_number in seat_numbers:
                raise InflightCollectionBlocked("duplicate persisted seat number")
            seat_ids.add(seat.seat_id)
            seat_numbers.add(seat.seat_number)
            used_seats.add(seat.seat_id)
            if seat.session_id:
                session = sessions.get(seat.session_id)
                if (
                    session is None
                    or session.cluster_ref != reservation.cluster_ref
                    or session.tenant_id != workshop.tenant_id
                    or session.catalog_item_id != reservation.catalog_id
                    or seat.session_id in used_sessions
                ):
                    raise InflightCollectionBlocked("persisted seat session identity mismatch")
                linked_sessions.add(seat.session_id)
                used_sessions.add(seat.session_id)
        if seat_numbers != set(range(1, workshop.num_users + 1)):
            raise InflightCollectionBlocked("persisted seat number roster incomplete")
        if set(workshop.session_ids) != linked_sessions or len(workshop.session_ids) != len(
            linked_sessions
        ):
            raise InflightCollectionBlocked("persisted workshop session roster incomplete")
        result[workshop_id] = seat_ids
    return result
