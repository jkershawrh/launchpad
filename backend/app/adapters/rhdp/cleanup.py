from __future__ import annotations

import logging
import os
import time

from app.adapters.rhdp.sandbox_api import SandboxAPIClient, SandboxAPIError

logger = logging.getLogger(__name__)

CLEANUP_POLL_TIMEOUT = int(os.environ.get("SANDBOX_CLEANUP_POLL_TIMEOUT", "60"))
CLEANUP_POLL_INTERVAL = 5


class RHDPCleanupAdapter:
    """Releases Sandbox API placements on session reclaim."""

    def __init__(self, sandbox_api: SandboxAPIClient | None = None):
        self._api = sandbox_api or SandboxAPIClient()

    def cleanup(self, identifier: str) -> None:
        try:
            self._api.delete_placement(identifier)
            logger.info("Requested cleanup of sandbox placement: %s", identifier)
        except SandboxAPIError as e:
            if e.status_code == 404:
                logger.info("Placement %s already deleted", identifier)
                return
            else:
                logger.error("Failed to cleanup placement %s: %s", identifier, e)
                raise

        self._wait_for_deletion(identifier)

    def _wait_for_deletion(self, identifier: str) -> None:
        """Poll until placement is actually gone (DELETE returns 202 = async)."""
        deadline = time.time() + CLEANUP_POLL_TIMEOUT
        while time.time() < deadline:
            try:
                self._api.get_placement(identifier)
                time.sleep(CLEANUP_POLL_INTERVAL)
            except SandboxAPIError as e:
                if e.status_code == 404:
                    logger.info("Confirmed cleanup of placement: %s", identifier)
                    return
                logger.warning("Unexpected error polling placement %s: %s", identifier, e)
                return
        logger.warning("Placement %s not confirmed deleted after %ds, proceeding anyway", identifier, CLEANUP_POLL_TIMEOUT)
