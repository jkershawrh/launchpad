from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import httpx
from pydantic import BaseModel, Field

from app.domain.models import CatalogItem

logger = logging.getLogger("launchpad.preflight")


class PreflightCheck(BaseModel):
    name: str
    status: str  # pass, fail, skip
    message: str


class PreflightResult(BaseModel):
    passed: bool
    checks: List[PreflightCheck] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LiteLLMPreflightChecker:

    def __init__(self, api_base: str) -> None:
        self._api_base = api_base.rstrip("/")

    def check(self, catalog_item: CatalogItem) -> PreflightResult:
        required_models = catalog_item.metadata.get("required_models", [])
        if not required_models:
            return PreflightResult(passed=True, checks=[])

        try:
            resp = httpx.get(f"{self._api_base}/models", timeout=10)
            resp.raise_for_status()
            available = {m["id"] for m in resp.json().get("data", [])}
        except Exception as e:
            logger.warning("LiteLLM unreachable at %s: %s", self._api_base, e)
            return PreflightResult(
                passed=False,
                checks=[
                    PreflightCheck(
                        name="litellm-connectivity",
                        status="fail",
                        message=f"LiteLLM unreachable at {self._api_base}: connection error",
                    )
                ],
            )

        checks: List[PreflightCheck] = []
        for model in required_models:
            if model in available:
                checks.append(PreflightCheck(name=f"model:{model}", status="pass", message=f"Model {model} available"))
            else:
                checks.append(PreflightCheck(name=f"model:{model}", status="fail", message=f"Model {model} not found in LiteLLM at {self._api_base}"))

        passed = all(c.status == "pass" for c in checks)
        return PreflightResult(passed=passed, checks=checks)


class MockPreflightAdapter:

    def check(self, catalog_item: CatalogItem) -> PreflightResult:
        return PreflightResult(passed=True, checks=[])
