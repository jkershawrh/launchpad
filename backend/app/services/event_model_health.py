"""Fail-closed assessment of current model serving evidence."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from app.domain.event_model_health import EventModelHealthSnapshot
from app.domain.events import EventRecord


@dataclass(frozen=True)
class ModelHealthAssessment:
    status: str
    explanation: str
    snapshot_id: str | None = None


class EventModelHealthUnavailableError(RuntimeError):
    """Configured runtime evidence cannot be trusted or read."""


class FileEventModelHealthProvider:
    """Read a server-managed JSON snapshot, never a requester-supplied payload."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> EventModelHealthSnapshot:
        import json

        try:
            raw = self.path.read_bytes()
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("schema_version") != "1.0":
                raise ValueError("unsupported runtime model health schema")
            return EventModelHealthSnapshot.model_validate(
                {
                    "snapshot_id": "sha256:" + sha256(raw).hexdigest(),
                    "observed_at": document["observed_at"],
                    "models": document["models"],
                }
            )
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            raise EventModelHealthUnavailableError(
                "Configured runtime model health evidence is unavailable"
            ) from exc


def assess_event_model_health(
    record: EventRecord,
    snapshot: EventModelHealthSnapshot | None,
    now: datetime,
) -> ModelHealthAssessment:
    """Require a responsive route and ready replica for each allocated model."""

    labs = {item.lab_ref: item for item in record.manifest.labs}
    required = {
        (allocation.cluster_id, model_id)
        for allocation in record.capacity_preview.allocations
        for model_id in labs[allocation.lab_ref].required_models
    }
    if not required:
        return ModelHealthAssessment("not_required", "No runtime model gate is required")
    if snapshot is None:
        return ModelHealthAssessment("blocked", "Runtime model health evidence is unavailable")
    age = (now - snapshot.observed_at).total_seconds()
    if age > 120:
        return ModelHealthAssessment("blocked", "Runtime model health evidence is stale", snapshot.snapshot_id)
    if age < -30:
        return ModelHealthAssessment("blocked", "Runtime model health evidence is future-dated", snapshot.snapshot_id)

    observed = {(item.cluster_id, item.model_id): item for item in snapshot.models}
    for cluster_id, model_id in sorted(required):
        item = observed.get((cluster_id, model_id))
        if item is None:
            reason = "missing"
        elif item.ready_replicas < 1:
            reason = "no ready replica"
        elif not item.route_exposed:
            reason = "route is not exposed"
        elif not item.probe_success:
            reason = "inference probe failed"
        else:
            continue
        return ModelHealthAssessment(
            "blocked", f"Runtime model {model_id} on {cluster_id}: {reason}", snapshot.snapshot_id
        )
    return ModelHealthAssessment("ready", "All required model routes are responsive", snapshot.snapshot_id)
