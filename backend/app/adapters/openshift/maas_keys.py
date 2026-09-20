from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.models import MaaSKeyRevocationReceipt


@dataclass(frozen=True)
class MaaSKey:
    key: str
    key_id: str = ""


class LiteLLMVirtualKeyBroker:
    """Issue and revoke scoped LiteLLM virtual keys for lab sessions."""

    def __init__(self, api_base: str, master_key: str, timeout: float = 10) -> None:
        if not api_base or not master_key:
            raise ValueError("LiteLLM virtual-key broker requires API base and master key")
        self.api_base = api_base.rstrip("/")
        self.master_key = master_key
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.master_key}"}

    def create_key(
        self,
        *,
        alias: str,
        duration: str,
        models: Iterable[str],
        rpm_limit: int,
        metadata: dict[str, Any],
    ) -> MaaSKey:
        response = httpx.post(
            f"{self.api_base}/key/generate",
            headers=self._headers,
            json={
                "key_alias": alias,
                "duration": duration,
                "models": list(models),
                "rpm_limit": rpm_limit,
                "metadata": metadata,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        key = payload.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("LiteLLM key generation returned no key")
        return MaaSKey(key=key, key_id=str(payload.get("token_id") or ""))

    def revoke_key(
        self, key: str, *, key_id: str
    ) -> MaaSKeyRevocationReceipt | None:
        if not key:
            return None
        response = httpx.post(
            f"{self.api_base}/key/delete",
            headers=self._headers,
            json={"keys": [key]},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._revocation_receipt(response, key_id=key_id)

    def revoke_key_by_alias(
        self, key_alias: str, *, key_id: str
    ) -> MaaSKeyRevocationReceipt | None:
        """Revoke a key without retaining or recovering its secret value."""

        if not key_alias:
            return None
        response = httpx.post(
            f"{self.api_base}/key/delete",
            headers=self._headers,
            json={"key_aliases": [key_alias]},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._revocation_receipt(response, key_id=key_id)

    @staticmethod
    def _revocation_receipt(
        response: httpx.Response, *, key_id: str
    ) -> MaaSKeyRevocationReceipt:
        confirmation_id = response.headers.get("x-request-id", "").strip()
        return MaaSKeyRevocationReceipt(
            provider="litellm",
            key_id=key_id,
            confirmed_at=datetime.now(UTC),
            confirmation_id=confirmation_id or "http-success",
        )
