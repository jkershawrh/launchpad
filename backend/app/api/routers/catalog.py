from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.auth.oauth import get_current_user

from app.api.deps import catalog_adapter
from app.domain.models import CatalogItem

router = APIRouter(dependencies=[Depends(get_current_user)], prefix="/catalog", tags=["catalog"])


@router.get("", response_model=List[CatalogItem])
def list_catalog():
    return catalog_adapter.list_items()


@router.get("/{catalog_item_id}", response_model=CatalogItem)
def get_catalog_item(catalog_item_id: str):
    item = catalog_adapter.get_item(catalog_item_id)
    if not item:
        raise HTTPException(404, f"Catalog item {catalog_item_id} not found")
    return item
