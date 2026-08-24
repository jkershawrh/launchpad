from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

import yaml

from app.domain.enums import CatalogStatus
from app.domain.models import CatalogItem

logger = logging.getLogger("launchpad.file_catalog")


class FileCatalogAdapter:
    """Reads CatalogItem definitions from YAML files in a directory tree.

    Expected structure:
        catalog_dir/
            demo-a/
                catalog-item.yaml
            demo-b/
                catalog-item.yaml
    """

    def __init__(self, catalog_dir: str) -> None:
        self._catalog_dir = catalog_dir
        self._items: Dict[str, CatalogItem] = {}
        self._scan()

    def _scan(self) -> None:
        items: Dict[str, CatalogItem] = {}
        if not os.path.isdir(self._catalog_dir):
            logger.warning("Catalog directory does not exist: %s", self._catalog_dir)
            self._items = items
            return

        for entry in os.listdir(self._catalog_dir):
            subdir = os.path.join(self._catalog_dir, entry)
            if not os.path.isdir(subdir):
                continue
            yaml_path = os.path.join(subdir, "catalog-item.yaml")
            if not os.path.isfile(yaml_path):
                continue
            try:
                with open(yaml_path, "r") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    logger.warning("Skipping %s: not a YAML mapping", yaml_path)
                    continue
                item = CatalogItem(**data)
                items[item.catalog_item_id] = item
            except yaml.YAMLError as e:
                logger.warning("Skipping %s: invalid YAML: %s", yaml_path, e)
            except Exception as e:
                logger.warning("Skipping %s: validation error: %s", yaml_path, e)

        added = set(items) - set(self._items)
        removed = set(self._items) - set(items)
        if added:
            logger.info("Catalog: added %s", ", ".join(sorted(added)))
        if removed:
            logger.info("Catalog: removed %s", ", ".join(sorted(removed)))

        self._items = items

    def reload(self) -> None:
        self._scan()

    def list_items(self) -> List[CatalogItem]:
        return list(self._items.values())

    def get_item(self, catalog_item_id: str) -> Optional[CatalogItem]:
        return self._items.get(catalog_item_id)

    def validate_item(self, catalog_item_id: str) -> bool:
        item = self._items.get(catalog_item_id)
        return item is not None and item.status == CatalogStatus.ACTIVE

    def set_status(self, catalog_item_id: str, status: CatalogStatus) -> CatalogItem:
        item = self._items.get(catalog_item_id)
        if not item:
            raise ValueError(f"Catalog item {catalog_item_id} not found")
        updated = item.model_copy(update={"status": status})
        self._items[catalog_item_id] = updated
        return updated
