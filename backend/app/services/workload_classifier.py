from __future__ import annotations

import logging
from typing import List, Optional

from app.domain.models import CatalogItem, LabRequest
from app.domain.workload import HardwareMatch, WorkloadProfile, WorkloadType

logger = logging.getLogger("launchpad.workload_classifier")

HARDWARE_PROFILES = ["gaudi-direct", "gaudi-endpoint", "mixed-overdrive", "xeon6", "xeon-basic"]

WORKLOAD_HARDWARE_SCORES = {
    WorkloadType.TRAINING: {
        "gaudi-direct": 95, "gaudi-endpoint": 60, "mixed-overdrive": 75,
        "xeon6": 30, "xeon-basic": 20,
    },
    WorkloadType.GPU_INFERENCE: {
        "gaudi-endpoint": 95, "gaudi-direct": 70, "mixed-overdrive": 80,
        "xeon6": 40, "xeon-basic": 30,
    },
    WorkloadType.RAG_PIPELINE: {
        "gaudi-endpoint": 85, "mixed-overdrive": 90, "gaudi-direct": 60,
        "xeon6": 50, "xeon-basic": 40,
    },
    WorkloadType.AGENT: {
        "xeon-basic": 70, "xeon6": 80, "gaudi-endpoint": 85,
        "mixed-overdrive": 75, "gaudi-direct": 50,
    },
    WorkloadType.CPU_INFERENCE: {
        "xeon-basic": 90, "xeon6": 95, "gaudi-endpoint": 40,
        "mixed-overdrive": 50, "gaudi-direct": 30,
    },
    WorkloadType.LIGHTWEIGHT: {
        "xeon-basic": 95, "xeon6": 80, "gaudi-endpoint": 30,
        "mixed-overdrive": 40, "gaudi-direct": 20,
    },
    WorkloadType.MIXED: {
        "mixed-overdrive": 95, "gaudi-endpoint": 75, "gaudi-direct": 70,
        "xeon6": 50, "xeon-basic": 35,
    },
}

INTENSITY_TO_QUOTA = {
    ("high", "high"): "large",
    ("high", "medium"): "large",
    ("medium", "high"): "large",
    ("medium", "medium"): "standard",
    ("medium", "low"): "standard",
    ("low", "medium"): "standard",
    ("low", "low"): "small",
}


class WorkloadClassifier:

    def classify(self, catalog_item: CatalogItem, request: LabRequest) -> WorkloadProfile:
        caps = set(catalog_item.required_capabilities)
        hw = catalog_item.default_hardware_profile or ""
        meta = catalog_item.metadata or {}

        if meta.get("cpu_only"):
            return WorkloadProfile(
                workload_type=WorkloadType.CPU_INFERENCE,
                compute_intensity="medium",
                memory_intensity="low",
                gpu_required=False,
                gpu_mode="none",
                io_pattern="interactive",
                confidence=0.9,
                classification_source="catalog_metadata",
            )

        if hw == "mixed-overdrive" and len(caps) >= 3:
            return WorkloadProfile(
                workload_type=WorkloadType.MIXED,
                compute_intensity="high",
                memory_intensity="high",
                gpu_required=True,
                gpu_mode="endpoint",
                io_pattern="interactive",
                confidence=0.8,
                classification_source="catalog_metadata",
            )

        if "gaudi_direct" in caps:
            return WorkloadProfile(
                workload_type=WorkloadType.TRAINING,
                compute_intensity="high",
                memory_intensity="high",
                gpu_required=True,
                gpu_mode="direct",
                io_pattern="batch",
                confidence=0.9,
                classification_source="catalog_metadata",
            )

        if "vector_db" in caps:
            return WorkloadProfile(
                workload_type=WorkloadType.RAG_PIPELINE,
                compute_intensity="medium",
                memory_intensity="high",
                gpu_required="model_endpoint" in caps,
                gpu_mode="endpoint" if "model_endpoint" in caps else "none",
                io_pattern="interactive",
                confidence=0.9,
                classification_source="catalog_metadata",
            )

        if hw == "gaudi-direct":
            return WorkloadProfile(
                workload_type=WorkloadType.TRAINING,
                compute_intensity="high",
                memory_intensity="high",
                gpu_required=True,
                gpu_mode="direct",
                io_pattern="batch",
                confidence=0.7,
                classification_source="rules",
            )

        if hw == "gaudi-endpoint" or "model_endpoint" in caps:
            return WorkloadProfile(
                workload_type=WorkloadType.GPU_INFERENCE,
                compute_intensity="high" if hw == "gaudi-endpoint" else "medium",
                memory_intensity="medium",
                gpu_required=True,
                gpu_mode="endpoint",
                io_pattern="interactive",
                confidence=0.7,
                classification_source="rules",
            )

        quota = catalog_item.default_quota_profile or ""
        if hw == "xeon-basic" and quota == "small":
            return WorkloadProfile(
                workload_type=WorkloadType.LIGHTWEIGHT,
                compute_intensity="low",
                memory_intensity="low",
                gpu_required=False,
                gpu_mode="none",
                io_pattern="interactive",
                confidence=0.8,
                classification_source="rules",
            )

        if hw in ("xeon-basic", "xeon6"):
            return WorkloadProfile(
                workload_type=WorkloadType.CPU_INFERENCE,
                compute_intensity="medium",
                memory_intensity="medium",
                gpu_required=False,
                gpu_mode="none",
                io_pattern="interactive",
                confidence=0.6,
                classification_source="rules",
            )

        return WorkloadProfile(
            workload_type=WorkloadType.CPU_INFERENCE,
            compute_intensity="medium",
            memory_intensity="medium",
            gpu_required=False,
            gpu_mode="none",
            io_pattern="interactive",
            confidence=0.4,
            classification_source="rules",
        )

    def match_hardware(self, profile: WorkloadProfile) -> List[HardwareMatch]:
        scores = WORKLOAD_HARDWARE_SCORES.get(profile.workload_type, {})

        matches = []
        for hw in HARDWARE_PROFILES:
            base_score = scores.get(hw, 30)

            reasons = []
            if profile.gpu_required and hw in ("gaudi-endpoint", "gaudi-direct", "mixed-overdrive"):
                reasons.append("GPU capability available")
            elif not profile.gpu_required and hw in ("xeon-basic", "xeon6"):
                reasons.append("CPU-only matches workload")

            if profile.compute_intensity == "high" and hw in ("gaudi-direct", "gaudi-endpoint", "mixed-overdrive"):
                reasons.append("high compute capacity")
            elif profile.compute_intensity == "low" and hw == "xeon-basic":
                reasons.append("lightweight profile matches")

            quota = self.right_size_quota(profile, None)

            matches.append(HardwareMatch(
                hardware_profile=hw,
                score=float(base_score),
                reasons=reasons or [f"default score for {profile.workload_type.value}"],
                right_sized_quota=quota,
            ))

        matches.sort(key=lambda m: -m.score)
        return matches

    def right_size_quota(
        self, profile: WorkloadProfile, catalog_item: Optional[CatalogItem]
    ) -> str:
        if profile.gpu_required and profile.compute_intensity == "high":
            return "large"

        key = (profile.compute_intensity, profile.memory_intensity)
        return INTENSITY_TO_QUOTA.get(key, "standard")
