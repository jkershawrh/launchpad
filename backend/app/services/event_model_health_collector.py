"""Opt-in, server-side producer for short-lived event model-health evidence.

This module has no scheduler or implicit network activity. A trusted operator must
configure targets and invoke it; the admission reader remains independently
fail-closed when the resulting snapshot is absent or stale.
"""

import json
import os
import re
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.event_model_health import EventModelHealthSnapshot


class ModelProbeTarget(BaseModel):
    """Server-owned probe specification; credentials are environment references."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    readiness_url: str
    route_url: str
    inference_url: str
    inference_body: dict[str, Any]
    response_model_id: str | None = None
    readiness_token_env: str | None = None
    route_token_env: str | None = None
    inference_token_env: str | None = None

    @field_validator("readiness_url", "route_url", "inference_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        url = httpx.URL(value)
        if url.scheme != "https" or not url.host or url.username or url.password or url.query:
            raise ValueError("probe URL must be an HTTPS endpoint without credentials or query")
        return value

    @field_validator("response_model_id")
    @classmethod
    def validate_response_model_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("response model identity must not be empty")
        return value

    @field_validator("readiness_token_env", "route_token_env", "inference_token_env")
    @classmethod
    def validate_token_name(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("credential must be an environment variable name")
        return value


class ModelHealthCollector:
    """Probe each target once; errors become negative evidence, never synthetic health."""

    def __init__(self, *, client: httpx.Client, now: Callable[[], datetime] | None = None) -> None:
        self.client = client
        self.now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _headers(env_name: str | None) -> dict[str, str]:
        if env_name is None:
            return {}
        token = os.environ.get(env_name)
        if not token:
            raise ValueError("Configured model probe credential is unavailable")
        return {"Authorization": f"Bearer {token}"}

    def collect(self, targets: Sequence[ModelProbeTarget]) -> dict[str, Any]:
        if not targets:
            raise ValueError("at least one model probe target is required")
        keys = [(target.cluster_id, target.model_id) for target in targets]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate cluster/model probe target")
        started = self.now()
        if started.tzinfo is None:
            raise ValueError("collector clock must be timezone-aware")
        rows = []
        for target in targets:
            # Resolve all credentials before probing, so a missing secret cannot
            # be interpreted as an ordinary endpoint failure.
            ready_headers = self._headers(target.readiness_token_env)
            route_headers = self._headers(target.route_token_env)
            inference_headers = self._headers(target.inference_token_env)
            replicas = 0
            exposed = False
            responded = False
            try:
                response = self.client.get(target.readiness_url, headers=ready_headers)
                if response.status_code == 200:
                    status = response.json()
                    raw = status.get("ready_replicas")
                    if (
                        status.get("cluster_id") == target.cluster_id
                        and status.get("model_id") == target.model_id
                        and type(raw) is int
                        and raw >= 0
                    ):
                        replicas = raw
            except (httpx.HTTPError, ValueError, AttributeError, TypeError):
                pass
            try:
                response = self.client.get(target.route_url, headers=route_headers)
                exposed = response.status_code == 200
            except httpx.HTTPError:
                pass
            try:
                response = self.client.post(
                    target.inference_url, headers=inference_headers, json=target.inference_body
                )
                if response.status_code == 200:
                    result = response.json()
                    choices = result.get("choices")
                    expected_model = target.response_model_id or target.model_id
                    if (
                        result.get("model") == expected_model
                        and isinstance(choices, list)
                        and choices
                    ):
                        message = choices[0].get("message")
                        content = message.get("content") if isinstance(message, dict) else None
                        responded = isinstance(content, str) and bool(content.strip())
            except (httpx.HTTPError, ValueError, AttributeError, TypeError, IndexError):
                pass
            rows.append(
                {
                    "cluster_id": target.cluster_id,
                    "model_id": target.model_id,
                    "ready_replicas": replicas,
                    "route_exposed": exposed,
                    "probe_success": responded,
                }
            )
        if (self.now() - started).total_seconds() > 120:
            raise ValueError("model-health collection took too long for fresh evidence")
        return {"schema_version": "1.0", "observed_at": started.isoformat(), "models": rows}


def write_model_health_snapshot(path: str | Path, document: dict[str, Any]) -> None:
    """Validate and replace exactly one configured file without partial writes."""

    if document.get("schema_version") != "1.0":
        raise ValueError("unsupported runtime model health schema")
    EventModelHealthSnapshot.model_validate(
        {
            "snapshot_id": "sha256:" + "0" * 64,
            "observed_at": document["observed_at"],
            "models": document["models"],
        }
    )
    destination = Path(path)
    if destination.is_symlink():
        raise ValueError("snapshot destination must not be a symlink")
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temp_path = temporary.name
            os.fchmod(temporary.fileno(), 0o600)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)


def load_model_probe_targets(path: str | Path) -> list[ModelProbeTarget]:
    """Load explicit probe targets from a trusted, local configuration file."""

    document = json.loads(Path(path).read_text())
    if not isinstance(document, dict) or set(document) != {"schema_version", "targets"}:
        raise ValueError("invalid model probe configuration")
    if document["schema_version"] != "1.0" or not isinstance(document["targets"], list):
        raise ValueError("unsupported model probe configuration")
    return [ModelProbeTarget.model_validate(item) for item in document["targets"]]
