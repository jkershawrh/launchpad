from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class WorkloadType(str, Enum):
    CPU_INFERENCE = "cpu_inference"
    GPU_INFERENCE = "gpu_inference"
    TRAINING = "training"
    RAG_PIPELINE = "rag_pipeline"
    AGENT = "agent"
    MIXED = "mixed"
    LIGHTWEIGHT = "lightweight"


class WorkloadProfile(BaseModel):
    workload_type: WorkloadType
    compute_intensity: Literal["low", "medium", "high"] = "medium"
    memory_intensity: Literal["low", "medium", "high"] = "medium"
    gpu_required: bool = False
    gpu_mode: str = "none"
    io_pattern: Literal["batch", "streaming", "interactive"] = "interactive"
    estimated_vram_gb: Optional[int] = None
    estimated_cpu_cores: Optional[int] = None
    estimated_memory_gb: Optional[int] = None
    confidence: float = 0.5
    classification_source: Literal["catalog_metadata", "rules", "llm", "history"] = "rules"


class HardwareMatch(BaseModel):
    hardware_profile: str
    score: float = 0.0
    reasons: List[str] = Field(default_factory=list)
    right_sized_quota: Optional[str] = None
