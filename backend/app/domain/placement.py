from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ClusterCapacity(BaseModel):
    cluster_name: str
    score: float = 0.0
    cpu_utilization: Optional[float] = None
    gpu_available: Optional[bool] = None
    health_status: str = "unknown"
    active_sandboxes: int = 0
    vm_density: Optional[float] = None
    hot_nodes: int = 0
    health_rate: Optional[float] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class PlacementRecommendation(BaseModel):
    cluster_name: Optional[str] = None
    score: float = 0.0
    reasoning: str = ""
    fallback: bool = False
    source: Literal["cache", "live", "none"] = "none"


class PlacementDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    recommended_cluster: Optional[str] = None
    selected_cluster: Optional[str] = None
    hardware_profile: str
    score: float = 0.0
    decision_source: str = "none"
    reasoning: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
