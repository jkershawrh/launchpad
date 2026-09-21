"""Short-lived runtime evidence for model-dependent event admission."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ModelRuntimeHealth(BaseModel):
    cluster_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    ready_replicas: int = Field(ge=0)
    route_exposed: bool
    probe_success: bool


class EventModelHealthSnapshot(BaseModel):
    snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observed_at: datetime
    models: list[ModelRuntimeHealth]

    @model_validator(mode="after")
    def unique_models(self) -> "EventModelHealthSnapshot":
        if self.observed_at.tzinfo is None:
            raise ValueError("model health observed_at must include a timezone")
        keys = [(item.cluster_id, item.model_id) for item in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate cluster/model runtime evidence")
        return self
