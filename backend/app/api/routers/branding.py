from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.auth.oauth import get_current_user

from app.api.deps import branding_adapter
from app.domain.models import BrandingProfile

router = APIRouter(dependencies=[Depends(get_current_user)], prefix="/branding-profiles", tags=["branding"])


@router.get("", response_model=List[BrandingProfile])
def list_branding_profiles():
    return branding_adapter.list_profiles()


@router.get("/{branding_profile_id}", response_model=BrandingProfile)
def get_branding_profile(branding_profile_id: str):
    profile = branding_adapter.load_profile(branding_profile_id)
    if not profile:
        raise HTTPException(404, f"Branding profile {branding_profile_id} not found")
    return profile
