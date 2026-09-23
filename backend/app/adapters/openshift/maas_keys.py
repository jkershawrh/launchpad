from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from ssl import SSLContext
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


class RHOAIMaaSKeyBroker:
    """Issue and revoke subscription-bound Red Hat OpenShift AI MaaS keys."""

    attribution_mode = "rhoai_maas_api_key"

    def __init__(
        self,
        api_base: str,
        subscription: str,
        *,
        auth_token: str = "",
        auth_token_file: str = "",
        verify: SSLContext | str | bool = True,
        timeout: float = 10,
    ) -> None:
        if not api_base or not subscription:
            raise ValueError("RHOAI MaaS broker requires API base and subscription")
        if not auth_token and not auth_token_file:
            raise ValueError("RHOAI MaaS broker requires an authentication source")
        if verify is False:
            raise ValueError("RHOAI MaaS broker cannot disable TLS verification")
        self.api_base = api_base.rstrip("/")
        self.subscription = subscription
        self.auth_token = auth_token
        self.auth_token_file = auth_token_file
        self.verify = verify
        self.timeout = timeout

    @property
    def _api_keys_url(self) -> str:
        if self.api_base.endswith("/maas-api/v1"):
            return f"{self.api_base}/api-keys"
        if self.api_base.endswith("/maas-api"):
            return f"{self.api_base}/v1/api-keys"
        return f"{self.api_base}/maas-api/v1/api-keys"

    def _token(self) -> str:
        token = self.auth_token
        if self.auth_token_file:
            token = Path(self.auth_token_file).read_text(encoding="utf-8")
        token = token.strip()
        if not token:
            raise ValueError("RHOAI MaaS authentication source is empty")
        return token

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }

    def create_key(
        self,
        *,
        alias: str,
        duration: str,
        models: Iterable[str],
        rpm_limit: int,
        metadata: dict[str, Any],
    ) -> MaaSKey:
        # Model and rate limits are enforced by the server-owned subscription and
        # policy, not by client-provided key fields. Consume the values to make
        # that boundary explicit and keep this broker compatible with the
        # provisioning service's existing interface.
        del models, rpm_limit
        session_id = str(metadata.get("session_id") or "").strip()
        description = (
            f"Launchpad session {session_id}" if session_id else "Launchpad session"
        )
        response = httpx.post(
            self._api_keys_url,
            headers=self._headers,
            json={
                "name": alias,
                "description": description,
                "expiresIn": duration,
                "subscription": self.subscription,
            },
            verify=self.verify,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        key = payload.get("key")
        key_id = payload.get("id")
        if not isinstance(key, str) or not key:
            raise ValueError("RHOAI MaaS key generation returned no key")
        if not isinstance(key_id, str) or not key_id:
            raise ValueError("RHOAI MaaS key generation returned no key ID")
        return MaaSKey(key=key, key_id=key_id)

    def revoke_key(
        self, key: str, *, key_id: str
    ) -> MaaSKeyRevocationReceipt | None:
        if not key:
            return None
        if not key_id:
            raise ValueError("RHOAI MaaS key revocation requires a key ID")
        response = httpx.delete(
            f"{self._api_keys_url}/{key_id}",
            headers=self._headers,
            verify=self.verify,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._revocation_receipt(response, key_id=key_id)

    def revoke_key_by_alias(
        self, key_alias: str, *, key_id: str
    ) -> MaaSKeyRevocationReceipt | None:
        """Recover cleanup using only the persisted non-secret alias and key ID."""

        if not key_alias:
            return None
        if not key_id:
            raise ValueError("RHOAI MaaS alias recovery requires a key ID")
        response = httpx.post(
            f"{self._api_keys_url}/search",
            headers=self._headers,
            json={"filters": {"includeEphemeral": True}},
            verify=self.verify,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise TypeError("RHOAI MaaS key search returned an invalid response")
        matches = [
            item
            for item in items
            if isinstance(item, dict)
            and item.get("id") == key_id
            and item.get("name") == key_alias
        ]
        if len(matches) != 1:
            raise ValueError("RHOAI MaaS key alias and ID did not resolve uniquely")
        if matches[0].get("status") == "revoked":
            return MaaSKeyRevocationReceipt(
                provider="rhoai-maas",
                key_id=key_id,
                confirmed_at=datetime.now(UTC),
                confirmation_id="already-revoked",
            )
        return self.revoke_key("alias-recovery", key_id=key_id)

    @staticmethod
    def _revocation_receipt(
        response: httpx.Response, *, key_id: str
    ) -> MaaSKeyRevocationReceipt:
        confirmation_id = response.headers.get("x-request-id", "").strip()
        return MaaSKeyRevocationReceipt(
            provider="rhoai-maas",
            key_id=key_id,
            confirmed_at=datetime.now(UTC),
            confirmation_id=confirmation_id or "http-success",
        )
