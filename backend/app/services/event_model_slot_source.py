"""Explicit, local-only model-slot evidence for future event inventory.

This is a structured-file boundary, not a capacity estimator or live collector.
The producer must prove its own promoted concurrency policy and write one
cluster-specific observation; ready replicas and model health are insufficient
to infer the number of simultaneous inference slots. No admission wiring here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.clusters import ClusterTarget
from app.services.event_inflight_capacity_collector import InflightCollectionBlocked
from app.services.event_kubernetes_inventory_observer import ModelSlotObservation

_FIELDS = {
    "schema_version",
    "cluster_id",
    "observed_at",
    "basis",
    "capacity_policy_ref",
    "allocatable_slots",
    "complete",
}
_MAX_BYTES = 64 * 1024


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate model slot evidence key")
        document[key] = value
    return document


class FileModelSlotSource:
    """Read one explicitly configured cluster observation without fallback.

    The optional clock supports deterministic local tests. The same freshness
    window as KubernetesClusterInventoryObserver is enforced here, too.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.path = Path(path)
        self.clock = clock

    def observe_model_slots(self, target: ClusterTarget) -> ModelSlotObservation:
        try:
            if self.path.is_symlink() or not self.path.is_file():
                raise ValueError("model slot evidence file is unavailable")
            if self.path.stat().st_size > _MAX_BYTES:
                raise ValueError("model slot evidence file exceeds size limit")
            document = json.loads(self.path.read_bytes(), object_pairs_hook=_unique_pairs)
            if type(document) is not dict or set(document) != _FIELDS:
                raise ValueError("model slot evidence shape is incomplete")
            if document["schema_version"] != "1.0":
                raise ValueError("model slot evidence schema is unsupported")
            if (
                document["cluster_id"] != target.cluster_id
                or type(document["cluster_id"]) is not str
            ):
                raise ValueError("model slot evidence target mismatch")
            if document["basis"] != "promoted-model-concurrency":
                raise ValueError("model slot evidence basis is untrusted")
            policy = document["capacity_policy_ref"]
            if type(policy) is not str or not policy or policy.strip() != policy:
                raise ValueError("model slot capacity policy reference is missing")
            slots = document["allocatable_slots"]
            if type(slots) is not int or slots < 0 or document["complete"] is not True:
                raise ValueError("model slot accounting is incomplete")
            raw_time = document["observed_at"]
            if type(raw_time) is not str:
                raise ValueError("model slot observation time is missing")
            observed_at = datetime.fromisoformat(raw_time)
            now = self.clock()
            if observed_at.tzinfo is None or not isinstance(now, datetime) or now.tzinfo is None:
                raise ValueError("model slot observation time requires timezone")
            if not -30 <= (now - observed_at).total_seconds() <= 120:
                raise ValueError("model slot evidence is stale or future-dated")
            return ModelSlotObservation(
                cluster_id=target.cluster_id,
                observed_at=observed_at,
                allocatable_slots=slots,
                complete=True,
            )
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise InflightCollectionBlocked(
                "model slot evidence is unavailable or incomplete"
            ) from exc
