"""Model health task — check LiteLLM model availability, toggle catalog item status."""

import logging
import os

import httpx
from celery import shared_task

from app.domain.enums import CatalogStatus

logger = logging.getLogger("launchpad.tasks.model_health")


def _do_model_health_check(catalog_adapter, litellm_base: str):
    try:
        resp = httpx.get(f"{litellm_base.rstrip('/')}/models", timeout=10)
        resp.raise_for_status()
        available = {m["id"] for m in resp.json().get("data", [])}
    except Exception as e:
        logger.warning("LiteLLM unreachable at %s: %s", litellm_base, e)
        return

    checked = 0
    toggled = 0
    for item in catalog_adapter.list_items():
        required = item.metadata.get("required_models", [])
        if not required:
            continue
        checked += 1
        all_healthy = all(m in available for m in required)

        if all_healthy and item.status == CatalogStatus.DRAFT:
            if hasattr(catalog_adapter, "set_status"):
                catalog_adapter.set_status(item.catalog_item_id, CatalogStatus.ACTIVE)
                toggled += 1
                logger.info("Model health: %s restored to active", item.catalog_item_id)
        elif not all_healthy and item.status == CatalogStatus.ACTIVE:
            missing = [m for m in required if m not in available]
            if hasattr(catalog_adapter, "set_status"):
                catalog_adapter.set_status(item.catalog_item_id, CatalogStatus.DRAFT)
                toggled += 1
                logger.info("Model health: %s set to draft (missing: %s)", item.catalog_item_id, missing)

    logger.info("Model health: checked %d items, toggled %d", checked, toggled)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def check_model_health(self):
    try:
        litellm_base = os.environ.get("LITELLM_API_BASE", "")
        if not litellm_base:
            logger.debug("Model health: LITELLM_API_BASE not set, skipping")
            return {"status": "skipped"}

        from app.api.deps import catalog_adapter
        _do_model_health_check(catalog_adapter, litellm_base)
        return {"status": "ok"}
    except Exception as e:
        logger.warning("Model health check failed (retry %d/%d): %s", self.request.retries, self.max_retries, e)
        raise self.retry(exc=e)
