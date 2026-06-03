"""Combined catalog — merges local seed catalog with Babylon CatalogItems.

Local items take precedence (they have richer metadata like hardware profiles,
capabilities, and provisioner_mode). Babylon items fill in the rest of the RHDP catalog.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.domain.enums import CatalogStatus
from app.domain.models import CatalogItem


class CombinedCatalogAdapter:

    def __init__(self, local_catalog, babylon_catalog=None):
        self._local = local_catalog
        self._babylon = babylon_catalog

    def list_items(self) -> List[CatalogItem]:
        items: Dict[str, CatalogItem] = {}
        if self._babylon:
            for item in self._babylon.list_items():
                if item.status != CatalogStatus.DEPRECATED:
                    items[item.catalog_item_id] = item
        for item in self._local.list_items():
            items[item.catalog_item_id] = item
        return list(items.values())

    def get_item(self, catalog_item_id: str) -> Optional[CatalogItem]:
        local = self._local.get_item(catalog_item_id)
        if local:
            return local
        if self._babylon:
            return self._babylon.get_item(catalog_item_id)
        return None

    def validate_item(self, catalog_item_id: str) -> bool:
        item = self.get_item(catalog_item_id)
        return item is not None and item.status == CatalogStatus.ACTIVE
