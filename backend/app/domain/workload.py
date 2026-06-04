from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class WorkloadType(str, Enum):
    # AI/ML workloads
    GPU_INFERENCE = "gpu_inference"
    CPU_INFERENCE = "cpu_inference"
    TRAINING = "training"
    RAG_PIPELINE = "rag_pipeline"
    AGENT = "agent"
    # Platform workloads
    VIRTUALIZATION = "virtualization"
    AUTOMATION = "automation"
    PLATFORM_OPS = "platform_ops"
    DEVELOPER = "developer"
    SECURITY = "security"
    EDGE = "edge"
    INFRASTRUCTURE = "infrastructure"
    CLOUD_ENV = "cloud_env"
    INTEGRATION = "integration"
    # General
    SANDBOX = "sandbox"
    WORKSHOP = "workshop"
    MIXED = "mixed"
    LIGHTWEIGHT = "lightweight"


class ResourceProfile(str, Enum):
    SHARED_NAMESPACE = "shared_namespace"
    DEDICATED_CLUSTER = "dedicated_cluster"
    VIRTUAL_MACHINE = "virtual_machine"
    CLOUD_INSTANCE = "cloud_instance"
    BARE_METAL = "bare_metal"
    GPU_ACCELERATED = "gpu_accelerated"
    MINIMAL = "minimal"


class WorkloadProfile(BaseModel):
    workload_type: WorkloadType
    resource_profile: ResourceProfile = ResourceProfile.SHARED_NAMESPACE
    compute_intensity: Literal["low", "medium", "high"] = "medium"
    memory_intensity: Literal["low", "medium", "high"] = "medium"
    gpu_required: bool = False
    gpu_mode: str = "none"
    io_pattern: Literal["batch", "streaming", "interactive"] = "interactive"
    estimated_vram_gb: Optional[int] = None
    estimated_cpu_cores: Optional[int] = None
    estimated_memory_gb: Optional[int] = None
    confidence: float = 0.5
    classification_source: Literal["catalog_metadata", "rules", "name_analysis", "llm", "history"] = "rules"


class HardwareMatch(BaseModel):
    hardware_profile: str
    score: float = 0.0
    reasons: List[str] = Field(default_factory=list)
    right_sized_quota: Optional[str] = None
