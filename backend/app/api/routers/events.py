from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_event_capacity_supply, get_event_manifest_store
from app.auth.oauth import get_current_user
from app.domain.events import (
    EventCapacityPreview,
    EventCapacitySupply,
    EventManifest,
    EventManifestConflictError,
    EventRecord,
    calculate_event_capacity,
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
