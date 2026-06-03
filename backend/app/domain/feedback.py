from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProvisioningOutcome(BaseModel):
    outcome_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    request_id: str
    catalog_item_id: str
    cluster_name: Optional[str] = None
    hardware_profile: str
    quota_profile: str
    workload_type: Optional[str] = None
    success: bool
    failure_reason: Optional[str] = None
    provision_latency_ms: int = 0
    validation_passed: bool = False
    session_duration_seconds: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackSummary(BaseModel):
    catalog_item_id: str
    cluster_name: str
    hardware_profile: str
    total_attempts: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    last_failure_reason: Optional[str] = None
    confidence: float = 0.0
    recommendation: Literal["preferred", "acceptable", "avoid"] = "acceptable"
