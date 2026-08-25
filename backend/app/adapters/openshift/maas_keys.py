from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import httpx


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
        metadata: dict[str, str],
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

    def revoke_key(self, key: str) -> None:
        if not key:
            return
        response = httpx.post(
            f"{self.api_base}/key/delete",
            headers=self._headers,
            json={"keys": [key]},
            timeout=self.timeout,
        )
        response.raise_for_status()
