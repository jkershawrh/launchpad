from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_event_capacity_supply
from app.auth.oauth import get_current_user
from app.domain.events import (
    EventCapacityPreview,
    EventCapacitySupply,
    EventManifest,
    calculate_event_capacity,
)

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
