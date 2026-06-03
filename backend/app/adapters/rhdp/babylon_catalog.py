"""Babylon catalog adapter — pull CatalogItems from the Babylon control plane.

Reads CatalogItem CRDs from babylon-catalog-prod/event/dev namespaces
on the Babylon control plane (ocp-us-east-1) using a kubeconfig.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Dict, List, Optional

from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem

logger = logging.getLogger("launchpad.babylon_catalog")

CATALOG_NAMESPACES = ["babylon-catalog-prod", "babylon-catalog-event", "babylon-catalog-dev"]
CACHE_TTL = 300


class BabylonCatalogAdapter:

    def __init__(self, kubeconfig_path: Optional[str] = None):
        self._kubeconfig = kubeconfig_path or os.environ.get("BABYLON_KUBECONFIG", "")
        self._cache: Dict[str, CatalogItem] = {}
        self._cache_updated: float = 0

    def list_items(self) -> List[CatalogItem]:
        self._refresh_if_stale()
        return list(self._cache.values())

    def get_item(self, catalog_item_id: str) -> Optional[CatalogItem]:
        self._refresh_if_stale()
        return self._cache.get(catalog_item_id)

    def validate_item(self, catalog_item_id: str) -> bool:
        item = self.get_item(catalog_item_id)
        return item is not None and item.status == CatalogStatus.ACTIVE

    def _refresh_if_stale(self) -> None:
        if time.time() - self._cache_updated < CACHE_TTL and self._cache:
            return
        self._refresh()

    def _refresh(self) -> None:
        if not self._kubeconfig or not os.path.exists(self._kubeconfig):
            logger.debug("No Babylon kubeconfig at %s", self._kubeconfig)
            return

        items: Dict[str, CatalogItem] = {}
        for ns in CATALOG_NAMESPACES:
            try:
                raw = subprocess.run(
                    ["oc", "get", "catalogitems", "-n", ns, "-o", "json"],
                    capture_output=True, text=True, timeout=30,
                    env={**os.environ, "KUBECONFIG": self._kubeconfig},
                )
                if raw.returncode != 0:
                    continue
                data = json.loads(raw.stdout)
                category_tag = ns.replace("babylon-catalog-", "")
                for cr in data.get("items", []):
                    item = self._parse_catalog_item(cr, category_tag)
                    if item:
                        items[item.catalog_item_id] = item
            except Exception as e:
                logger.debug("Failed to fetch from %s: %s", ns, e)

        if items:
            self._cache = items
            self._cache_updated = time.time()
            logger.info("Babylon catalog refreshed: %d items", len(items))

    def _parse_catalog_item(self, cr: Dict, category: str) -> Optional[CatalogItem]:
        try:
            meta = cr.get("metadata", {})
            spec = cr.get("spec", {})
            name = meta.get("name", "")
            display_name = spec.get("displayName", name)
            description = str(spec.get("description", "") or "")[:500]
            disabled = spec.get("disabled", False)
            provider = spec.get("provider", "")
            labels = meta.get("labels", {})

            cat = CatalogCategory.QUICK_START
            if "workshop" in name.lower() or "workshop" in display_name.lower():
                cat = CatalogCategory.GUIDED_BUILD
            elif "sandbox" in name.lower() or "cluster" in name.lower():
                cat = CatalogCategory.OPEN_SANDBOX

            return CatalogItem(
                catalog_item_id=name,
                display_name=display_name,
                description=description,
                category=cat,
                version="1.0.0",
                status=CatalogStatus.ACTIVE if not disabled else CatalogStatus.DEPRECATED,
                metadata={
                    "babylon_namespace": category,
                    "provider": provider,
                    "labels": labels,
                    "disabled": disabled,
                },
            )
        except Exception:
            return None
