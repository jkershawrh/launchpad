from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from app.adapters.interfaces import ConstraintResult
from app.domain.models import LabRequest

logger = logging.getLogger("launchpad.stargate.constraints")


class StarGateConstraintAdapter:
    """Pre-flight check: asks StarGate if provisioning is safe on the target cluster.

    Falls back to "allowed" if StarGate is unreachable — Launchpad works alone
    when StarGate is down.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.api_url = (api_url or os.environ.get("STARGATE_API_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("STARGATE_API_KEY", "")

    def evaluate(self, request: LabRequest) -> ConstraintResult:
        if not self.api_url:
            return ConstraintResult(allowed=True, level="allowed", reasons=[])

        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            resp = requests.get(
                f"{self.api_url}/integration/evaluate",
                params={
                    "catalog_item": request.catalog_item_id,
                    "tenant": request.tenant_id,
                },
                headers=headers,
                timeout=5,
            )

            if resp.status_code != 200:
                logger.warning("StarGate returned %d — falling back to allowed", resp.status_code)
                return ConstraintResult(allowed=True, level="allowed", reasons=[])

            data = resp.json()
            return ConstraintResult(
                allowed=data.get("allowed", True),
                level=data.get("level", "allowed"),
                reasons=data.get("reasons", []),
            )
        except Exception as e:
            logger.warning("StarGate unreachable (%s) — falling back to allowed", e)
            return ConstraintResult(allowed=True, level="allowed", reasons=[])
