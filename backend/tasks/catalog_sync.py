"""Catalog sync task — rescan CATALOG_DIR for new/changed/deleted demos."""

import logging

from celery import shared_task

logger = logging.getLogger("launchpad.tasks.catalog_sync")


def _do_catalog_sync(catalog_adapter):
    if hasattr(catalog_adapter, "reload"):
        catalog_adapter.reload()
        logger.info("Catalog sync: %d items loaded", len(catalog_adapter.list_items()))
    else:
        logger.debug("Catalog sync: adapter does not support reload, skipping")


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def sync_catalog(self):
    try:
        from app.api.deps import catalog_adapter
        _do_catalog_sync(catalog_adapter)
        return {"status": "ok", "items": len(catalog_adapter.list_items())}
    except Exception as e:
        logger.warning("Catalog sync failed (retry %d/%d): %s", self.request.retries, self.max_retries, e)
        raise self.retry(exc=e)
