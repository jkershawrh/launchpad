from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.domain.workload import WorkloadProfile


class DeepFieldSignal(BaseModel):
    cluster_name: str
    metric_type: str
    value: float
    threshold: float = 0.0
    status: Literal["normal", "warning", "critical"] = "normal"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class OrchestrationDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    workload_profile: Optional[WorkloadProfile] = None
    recommended_cluster: Optional[str] = None
    recommended_hardware: str = "xeon-basic"
    recommended_quota: str = "standard"
    confidence: float = 0.0
    rationale: str = ""
    signals_used: List[str] = Field(default_factory=list)
    fallback_chain: List[str] = Field(default_factory=list)
    decision_timestamp: datetime = Field(default_factory=datetime.utcnow)


class RebalanceAction(BaseModel):
    session_id: str
    from_cluster: str
    reason: str
    urgency: Literal["low", "medium", "high"] = "medium"


class HealthAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cluster_name: str
    alert_type: str
    severity: Literal["info", "warning", "critical"] = "warning"
    recommended_action: str = ""
    signals: List[DeepFieldSignal] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
