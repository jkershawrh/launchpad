"""Local trust anchor for an immutable, promoted model-concurrency policy.

The expected digest must be supplied independently of the observation and
policy files (for example, by a reviewed release configuration). A digest
copied from either file is not a trust anchor. This module performs no live
cluster access and does not certify a policy on its own.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_MAX_BYTES = 64 * 1024
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_POLICY_FIELDS = {
    "schema_version",
    "policy_id",
    "cluster_id",
    "model_id",
    "model_release",
    "max_concurrent_requests",
    "promotion_state",
    "approved_at",
    "approvers",
}


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate policy key")
        result[key] = value
    return result


def _identifier(value: Any) -> bool:
    return type(value) is str and bool(value) and value.strip() == value


@dataclass(frozen=True)
class PromotedModelConcurrencyPolicy:
    policy_id: str
    cluster_id: str
    model_id: str
    model_release: str
    max_concurrent_requests: int
    approved_at: datetime
    digest: str


class PinnedModelConcurrencyPolicy:
    """Read a policy whose exact bytes match an out-of-band approved digest."""

    def __init__(self, path: str | Path, *, trusted_digest: str) -> None:
        if type(trusted_digest) is not str or not _DIGEST.fullmatch(trusted_digest):
            raise ValueError("trusted policy digest must be an exact SHA-256 digest")
        self.path = Path(path)
        self.trusted_digest = trusted_digest

    def load(self) -> PromotedModelConcurrencyPolicy:
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("promoted policy file is unavailable")
        if self.path.stat().st_size > _MAX_BYTES:
            raise ValueError("promoted policy file exceeds size limit")
        source = self.path.read_bytes()
        digest = "sha256:" + hashlib.sha256(source).hexdigest()
        if digest != self.trusted_digest:
            raise ValueError("promoted policy digest does not match trust anchor")
        document = json.loads(source, object_pairs_hook=unique_pairs)
        if type(document) is not dict or set(document) != _POLICY_FIELDS:
            raise ValueError("promoted policy shape is incomplete")
        if document["schema_version"] != "1.0" or document["promotion_state"] != "promoted":
            raise ValueError("model concurrency policy is not promoted")
        for field in ("policy_id", "cluster_id", "model_id", "model_release"):
            if not _identifier(document[field]):
                raise ValueError(f"promoted policy {field} is invalid")
        ceiling = document["max_concurrent_requests"]
        if type(ceiling) is not int or ceiling < 0:
            raise ValueError("promoted policy capacity is invalid")
        approved_at = document["approved_at"]
        if type(approved_at) is not str or datetime.fromisoformat(approved_at).tzinfo is None:
            raise ValueError("promoted policy approval time requires timezone")
        approvers = document["approvers"]
        if (
            type(approvers) is not list
            or len(approvers) != 2
            or any(not _identifier(approver) for approver in approvers)
            or len(set(approvers)) != 2
        ):
            raise ValueError("promoted policy requires two distinct approvers")
        return PromotedModelConcurrencyPolicy(
            policy_id=document["policy_id"],
            cluster_id=document["cluster_id"],
            model_id=document["model_id"],
            model_release=document["model_release"],
            max_concurrent_requests=ceiling,
            approved_at=datetime.fromisoformat(approved_at),
            digest=digest,
        )
