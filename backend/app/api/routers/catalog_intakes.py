from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import catalog_intake_submission_service
from app.auth.oauth import require_admin
from app.domain.catalog_intake import CatalogIntakeDraft, CatalogIntakeSubmission

router = APIRouter(
    prefix="/admin/catalog-intakes",
    tags=["admin-catalog-intakes"],
    dependencies=[Depends(require_admin)],
)


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
