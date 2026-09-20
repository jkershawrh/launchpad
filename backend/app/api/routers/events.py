from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_event_capacity_supply,
    get_event_manifest_store,
    get_event_orchestration_service,
    get_event_reservation_ledger,
)
from app.auth.oauth import get_current_user, require_admin
from app.domain.events import (
    EventCapacityPreview,
    EventCapacitySupply,
    EventCleanupEvidenceResult,
    EventManifest,
    EventManifestConflictError,
    EventRecord,
    EventReservationCreate,
    EventReservationPlan,
    EventReservationReleaseRequest,
    EventReservationReleaseResult,
    EventStatusResult,
    EventWorkshopLaunchRequest,
    EventWorkshopLaunchResult,
    EventWorkshopPublicAccessResult,
    EventWorkshopReclaimResult,
    calculate_event_capacity,
)
from app.services.event_orchestration import (
    EventOrchestrationConflictError,
    EventOrchestrationService,
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


@router.get(
    "/{event_id}/status",
    response_model=EventStatusResult,
    dependencies=[Depends(require_admin)],
)
def get_event_status(
    event_id: str,
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
    orchestration: Annotated[
        EventOrchestrationService, Depends(get_event_orchestration_service)
    ],
) -> EventStatusResult:
    """Reconcile reservations, jobs, seats, and public access read-only."""

    record = store.get(event_id)
    if record is None:
        raise HTTPException(404, f"Approved event {event_id} was not found")
    try:
        return orchestration.status(record)
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Event status persistence is unavailable") from exc


@router.post(
    "/{event_id}/reclaim",
    response_model=EventWorkshopReclaimResult,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
def reclaim_event_workshops(
    event_id: str,
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
    orchestration: Annotated[
        EventOrchestrationService, Depends(get_event_orchestration_service)
    ],
) -> EventWorkshopReclaimResult:
    """Disable public access and queue bounded event cleanup."""

    record = store.get(event_id)
    if record is None:
        raise HTTPException(404, f"Approved event {event_id} was not found")
    try:
        return orchestration.reclaim(record)
    except (EventOrchestrationConflictError, EventReservationConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Event reclaim persistence is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/{event_id}/reclaim/finalize",
    response_model=EventCleanupEvidenceResult,
    dependencies=[Depends(require_admin)],
)
def finalize_event_cleanup(
    event_id: str,
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
    orchestration: Annotated[
        EventOrchestrationService, Depends(get_event_orchestration_service)
    ],
) -> EventCleanupEvidenceResult:
    """Release event capacity only after zero-residue proof."""

    record = store.get(event_id)
    if record is None:
        raise HTTPException(404, f"Approved event {event_id} was not found")
    try:
        return orchestration.finalize_cleanup(record)
    except (EventOrchestrationConflictError, EventReservationConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Cleanup evidence persistence is unavailable") from exc


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


@router.post(
    "/{event_id}/workshops/launch",
    response_model=EventWorkshopLaunchResult,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
def launch_event_workshops(
    event_id: str,
    request: EventWorkshopLaunchRequest,
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
    orchestration: Annotated[
        EventOrchestrationService, Depends(get_event_orchestration_service)
    ],
) -> EventWorkshopLaunchResult:
    """Consume all approved holds and queue deterministic workshop jobs.

    The request does not provision inside the API process. Public instructor
    codes remain pending until a separate post-readiness activation action.
    """

    record = store.get(event_id)
    if record is None:
        raise HTTPException(404, f"Approved event {event_id} was not found")
    try:
        return orchestration.launch(record, request)
    except (EventOrchestrationConflictError, EventReservationConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Event orchestration persistence is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post(
    "/{event_id}/workshops/{workshop_id}/public-access",
    response_model=EventWorkshopPublicAccessResult,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def activate_event_workshop_public_access(
    event_id: str,
    workshop_id: str,
    store: Annotated[EventManifestStore, Depends(get_event_manifest_store)],
    orchestration: Annotated[
        EventOrchestrationService, Depends(get_event_orchestration_service)
    ],
) -> EventWorkshopPublicAccessResult:
    """Return one instructor code after all reserved seats are ready."""

    record = store.get(event_id)
    if record is None:
        raise HTTPException(404, f"Approved event {event_id} was not found")
    try:
        return orchestration.activate_public_access(record, workshop_id)
    except EventOrchestrationConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except PersistenceUnavailableError as exc:
        raise HTTPException(503, "Public access persistence is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
