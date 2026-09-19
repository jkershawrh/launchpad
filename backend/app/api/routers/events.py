from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_event_capacity_supply,
    get_event_manifest_store,
    get_event_reservation_ledger,
)
from app.auth.oauth import get_current_user, require_admin
from app.domain.events import (
    EventCapacityPreview,
    EventCapacitySupply,
    EventManifest,
    EventManifestConflictError,
    EventRecord,
    EventReservationCreate,
    EventReservationPlan,
    EventReservationReleaseRequest,
    EventReservationReleaseResult,
    calculate_event_capacity,
)
from app.services.event_reservations import (
    EventReservationConflictError,
    EventReservationLedger,
    EventReservationUnavailableError,
    build_event_reservation_plan,
)
from app.services.events import EventManifestStore
from app.storage.stores import PersistenceUnavailableError

router = APIRouter(
    prefix="/events",
    tags=["events"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/capacity-preview", response_model=EventCapacityPreview)
def preview_event_capacity(
    manifest: EventManifest,
    supply: Annotated[EventCapacitySupply, Depends(get_event_capacity_supply)],
) -> EventCapacityPreview:
    """Calculate demand without reserving capacity or mutating live labs."""

    try:
        return calculate_event_capacity(manifest, supply)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("", response_model=EventRecord, status_code=201)
def create_approved_event(
    manifest: EventManifest,
    supply: Annotated[EventCapacitySupply, Depends(get_event_capacity_supply)],
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
) -> EventRecord:
    """Persist approved demand only after certified capacity covers it.

    This endpoint does not reserve capacity, create workshops, or mutate a
    cluster. A separate orchestration action must consume the immutable record.
    """

    try:
        preview = calculate_event_capacity(manifest, supply)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not preview.eligible:
        raise HTTPException(409, preview.explanation)
    try:
        return store.create(
            EventRecord(manifest=manifest, capacity_preview=preview)
        )
    except EventManifestConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Approved event persistence is unavailable") from exc


@router.post(
    "/{event_id}/reservations",
    response_model=EventReservationPlan,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def approve_event_reservation(
    event_id: str,
    request: EventReservationCreate,
    supply: Annotated[EventCapacitySupply, Depends(get_event_capacity_supply)],
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
    ledger: Annotated[
        EventReservationLedger, Depends(get_event_reservation_ledger)
    ],
) -> EventReservationPlan:
    """Atomically hold approved aggregate capacity without provisioning."""

    record = store.get(event_id)
    if record is None:
        raise HTTPException(404, f"Approved event {event_id} was not found")
    try:
        plan = build_event_reservation_plan(
            record,
            supply,
            expires_at=request.expires_at,
        )
        reservations = ledger.reserve(plan, supply)
        return plan.model_copy(update={"reservations": reservations})
    except (EventReservationConflictError, EventReservationUnavailableError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Event reservation persistence is unavailable") from exc


@router.post(
    "/{event_id}/reservations/release",
    response_model=EventReservationReleaseResult,
    dependencies=[Depends(require_admin)],
)
def release_event_reservation(
    event_id: str,
    request: EventReservationReleaseRequest,
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
    ledger: Annotated[
        EventReservationLedger, Depends(get_event_reservation_ledger)
    ],
) -> EventReservationReleaseResult:
    """Release capacity only after cleanup evidence has been produced."""

    if store.get(event_id) is None:
        raise HTTPException(404, f"Approved event {event_id} was not found")
    try:
        released = ledger.release(
            event_id,
            cleanup_evidence_id=request.cleanup_evidence_id,
        )
    except EventReservationConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Event reservation persistence is unavailable") from exc
    return EventReservationReleaseResult(
        event_id=event_id,
        released_reservations=released,
        cleanup_evidence_id=request.cleanup_evidence_id,
    )
