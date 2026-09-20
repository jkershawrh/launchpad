from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    catalog_intake_discovery_coordinator,
    catalog_intake_submission_service,
)
from app.auth.oauth import User, require_admin
from app.domain.catalog_intake import CatalogIntakeDraft, CatalogIntakeSubmission
from app.domain.catalog_intake_pipeline import CatalogIntakePipelineView
from app.services.catalog_intake_pipeline import build_catalog_intake_pipeline_view

router = APIRouter(
    prefix="/admin/catalog-intakes",
    tags=["admin-catalog-intakes"],
    dependencies=[Depends(require_admin)],
)
AdminUser = Annotated[User, Depends(require_admin)]


@router.post("", response_model=CatalogIntakeDraft, status_code=201)
def submit_catalog_intake(submission: CatalogIntakeSubmission) -> CatalogIntakeDraft:
    return catalog_intake_submission_service.submit(submission)


@router.get("", response_model=list[CatalogIntakeDraft])
def list_catalog_intakes() -> list[CatalogIntakeDraft]:
    return catalog_intake_submission_service.list_all()


@router.get("/{intake_id}", response_model=CatalogIntakeDraft)
def get_catalog_intake(intake_id: str) -> CatalogIntakeDraft:
    draft = catalog_intake_submission_service.get(intake_id)
    if draft is None:
        raise HTTPException(404, f"Catalog intake {intake_id} not found")
    return draft


@router.get("/{intake_id}/pipeline", response_model=CatalogIntakePipelineView)
def get_catalog_intake_pipeline(intake_id: str) -> CatalogIntakePipelineView:
    draft = catalog_intake_submission_service.get(intake_id)
    if draft is None:
        raise HTTPException(404, f"Catalog intake {intake_id} not found")
    return build_catalog_intake_pipeline_view(
        draft,
        isolated_worker_available=(
            catalog_intake_discovery_coordinator.dispatcher.available
        ),
    )


@router.post("/{intake_id}/source-approval", response_model=CatalogIntakeDraft)
def approve_catalog_intake_source(
    intake_id: str,
    user: AdminUser,
) -> CatalogIntakeDraft:
    try:
        return catalog_intake_submission_service.approve_source(
            intake_id, approved_by=user.username
        )
    except KeyError:
        raise HTTPException(404, f"Catalog intake {intake_id} not found") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{intake_id}/discovery", response_model=CatalogIntakeDraft)
def run_catalog_intake_discovery(
    intake_id: str,
    user: AdminUser,
) -> CatalogIntakeDraft:
    try:
        return catalog_intake_discovery_coordinator.start(
            intake_id, requested_by=user.username
        )
    except KeyError:
        raise HTTPException(404, f"Catalog intake {intake_id} not found") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
