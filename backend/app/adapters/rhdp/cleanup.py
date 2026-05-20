from __future__ import annotations

import logging

from app.adapters.rhdp.sandbox_api import SandboxAPIClient, SandboxAPIError

logger = logging.getLogger(__name__)


class RHDPCleanupAdapter:
    """Releases Sandbox API placements on session reclaim."""

    def __init__(self, sandbox_api: SandboxAPIClient | None = None):
        self._api = sandbox_api or SandboxAPIClient()

    def cleanup(self, identifier: str) -> None:
        try:
            self._api.delete_placement(identifier)
            logger.info("Released sandbox placement: %s", identifier)
        except SandboxAPIError as e:
            if e.status_code == 404:
                logger.info("Placement %s already deleted", identifier)
            else:
                logger.error("Failed to cleanup placement %s: %s", identifier, e)
                raise
