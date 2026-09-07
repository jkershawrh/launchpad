from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx
from httpx import HTTPError
from pydantic import BaseModel, Field

from app.domain.models import CatalogItem

logger = logging.getLogger("launchpad.preflight")


class PreflightCheck(BaseModel):
    name: str
    status: str  # pass, fail, skip
    message: str


class PreflightResult(BaseModel):
    passed: bool
    checks: list[PreflightCheck] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LiteLLMPreflightChecker:
    def __init__(
        self,
        api_base: str,
        api_key: str = "",
        *,
        max_attempts: int = 3,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds

    def check(
        self,
        catalog_item: CatalogItem,
        model_endpoints: dict[str, str] | None = None,
    ) -> PreflightResult:
        required_models = catalog_item.metadata.get("required_models", [])
        if not required_models:
            return PreflightResult(passed=True, checks=[])

        checks: list[PreflightCheck] = []
        endpoint_groups: dict[str, list[str]] = {}
        for model in required_models:
            if model_endpoints is not None:
                endpoint = model_endpoints.get(model, "").rstrip("/")
                if not endpoint:
                    checks.append(
                        PreflightCheck(
                            name=f"model:{model}",
                            status="fail",
                            message=f"No endpoint configured for model {model} on selected cluster",
                        )
                    )
                    continue
            else:
                endpoint = self._api_base
            endpoint_groups.setdefault(endpoint, []).append(model)

        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        for endpoint, models in endpoint_groups.items():
            available = None
            successful_attempt = 0
            for attempt in range(1, self._max_attempts + 1):
                try:
                    resp = httpx.get(f"{endpoint}/models", timeout=10, headers=headers)
                    resp.raise_for_status()
                    available = {m["id"] for m in resp.json().get("data", [])}
                    successful_attempt = attempt
                    break
                except (HTTPError, KeyError, TypeError, ValueError) as exc:
                    logger.warning(
                        "Model endpoint unreachable at %s on attempt %s of %s: %s",
                        endpoint,
                        attempt,
                        self._max_attempts,
                        exc,
                    )
                    if attempt < self._max_attempts:
                        time.sleep(self._retry_delay_seconds)

            if available is None:
                checks.extend(
                    PreflightCheck(
                        name=f"model:{model}",
                        status="fail",
                        message=(
                            f"Model endpoint unreachable at {endpoint} after "
                            f"{self._max_attempts} attempt(s): connection error"
                        ),
                    )
                    for model in models
                )
                continue

            for model in models:
                if model in available:
                    checks.append(
                        PreflightCheck(
                            name=f"model:{model}",
                            status="pass",
                            message=(
                                f"Model {model} available at {endpoint} "
                                f"(attempt {successful_attempt} of {self._max_attempts})"
                            ),
                        )
                    )
                else:
                    checks.append(
                        PreflightCheck(
                            name=f"model:{model}",
                            status="fail",
                            message=f"Model {model} not found at {endpoint}",
                        )
                    )

        passed = all(c.status == "pass" for c in checks)
        return PreflightResult(passed=passed, checks=checks)


class MockPreflightAdapter:
    def check(
        self,
        catalog_item: CatalogItem,
        model_endpoints: dict[str, str] | None = None,
    ) -> PreflightResult:
        return PreflightResult(passed=True, checks=[])
