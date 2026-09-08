from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LifecycleJobOperation(str, Enum):
    PROVISION_WORKSHOP = "provision_workshop"
    RECLAIM_WORKSHOP = "reclaim_workshop"
    PROVISION_SESSION = "provision_session"
    RECLAIM_SESSION = "reclaim_session"
    ENFORCE_TTL = "enforce_ttl"
    RECONCILE = "reconcile"


class LifecycleJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LifecycleJob(BaseModel):
    """Durable ownership record for one cluster lifecycle mutation."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    operation: LifecycleJobOperation
    aggregate_type: str
    aggregate_id: str
    cluster_ref: str | None = None
    status: LifecycleJobStatus = LifecycleJobStatus.QUEUED
    priority: int = Field(default=50, ge=0)
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    step: str = "queued"
    evidence: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=10, ge=1)
    owner_id: str | None = None
    lease_until: datetime | None = None
    fencing_token: int = Field(default=0, ge=0)
    next_attempt_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("aggregate_type", "aggregate_id", "idempotency_key")
    @classmethod
    def required_identifiers_are_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("lifecycle job identifiers must not be empty")
        return value


TERMINAL_LIFECYCLE_JOB_STATUSES = {
    LifecycleJobStatus.CANCELLED,
    LifecycleJobStatus.SUCCEEDED,
    LifecycleJobStatus.FAILED,
}
