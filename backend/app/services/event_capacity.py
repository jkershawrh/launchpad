"""Load server-owned, jointly approved event capacity certification."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.domain.events import EventCapacityMatrixDocument, EventCapacitySupply


class EventCapacityMatrixUnavailableError(RuntimeError):
    """Configured certification evidence cannot be loaded or trusted."""


class FileEventCapacityProvider:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> EventCapacitySupply:
        if not self.path.is_file():
            raise EventCapacityMatrixUnavailableError(
                f"Event capacity matrix does not exist: {self.path}"
            )
        try:
            source = self.path.read_bytes()
            payload = yaml.safe_load(source.decode("utf-8"))
            document = EventCapacityMatrixDocument.model_validate(payload)
        except (
            OSError,
            UnicodeDecodeError,
            yaml.YAMLError,
            ValidationError,
            TypeError,
        ) as exc:
            raise EventCapacityMatrixUnavailableError(
                f"Event capacity matrix is invalid: {exc}"
            ) from exc
        digest = f"sha256:{hashlib.sha256(source).hexdigest()}"
        return document.to_supply(digest)
