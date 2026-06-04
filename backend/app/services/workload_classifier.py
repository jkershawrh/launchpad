from __future__ import annotations

import logging
import re
from typing import List, Optional

from app.domain.models import CatalogItem, LabRequest
from app.domain.workload import HardwareMatch, ResourceProfile, WorkloadProfile, WorkloadType

logger = logging.getLogger("launchpad.workload_classifier")

HARDWARE_PROFILES = ["gaudi-direct", "gaudi-endpoint", "mixed-overdrive", "xeon6", "xeon-basic"]

DEFAULT_SCORES = {"gaudi-direct": 20, "gaudi-endpoint": 20, "mixed-overdrive": 30, "xeon6": 50, "xeon-basic": 60}

WORKLOAD_HARDWARE_SCORES = {
    WorkloadType.TRAINING: {"gaudi-direct": 95, "gaudi-endpoint": 60, "mixed-overdrive": 75, "xeon6": 30, "xeon-basic": 20},
    WorkloadType.GPU_INFERENCE: {"gaudi-endpoint": 95, "gaudi-direct": 70, "mixed-overdrive": 80, "xeon6": 40, "xeon-basic": 30},
    WorkloadType.RAG_PIPELINE: {"gaudi-endpoint": 85, "mixed-overdrive": 90, "gaudi-direct": 60, "xeon6": 50, "xeon-basic": 40},
    WorkloadType.AGENT: {"xeon-basic": 70, "xeon6": 80, "gaudi-endpoint": 85, "mixed-overdrive": 75, "gaudi-direct": 50},
    WorkloadType.CPU_INFERENCE: {"xeon-basic": 90, "xeon6": 95, "gaudi-endpoint": 40, "mixed-overdrive": 50, "gaudi-direct": 30},
    WorkloadType.LIGHTWEIGHT: {"xeon-basic": 95, "xeon6": 80, "gaudi-endpoint": 30, "mixed-overdrive": 40, "gaudi-direct": 20},
    WorkloadType.MIXED: {"mixed-overdrive": 95, "gaudi-endpoint": 75, "gaudi-direct": 70, "xeon6": 50, "xeon-basic": 35},
}

INTENSITY_TO_QUOTA = {
    ("high", "high"): "large", ("high", "medium"): "large", ("medium", "high"): "large",
    ("medium", "medium"): "standard", ("medium", "low"): "standard", ("low", "medium"): "standard",
    ("low", "low"): "small",
}

NAME_PATTERNS = [
    (WorkloadType.VIRTUALIZATION, ResourceProfile.VIRTUAL_MACHINE, [
        r'virt', r'migration', r'vmware', r'vm\b', r'cnv-blank', r'rosetta', r'vma',
        r'mig-factory', r'roadshow.*virt', r'virt.*roadshow',
    ]),
    (WorkloadType.AUTOMATION, ResourceProfile.SHARED_NAMESPACE, [
        r'ansible', r'\baap\b', r'\beda\b', r'playbook', r'automation.*controller',
        r'automation.*platform', r'casc', r'servicenow', r'windows.*automation',
    ]),
    (WorkloadType.GPU_INFERENCE, ResourceProfile.GPU_ACCELERATED, [
        r'gpu.*inference', r'vllm', r'llm-d', r'inference.*server', r'rhaiis',
    ]),
    (WorkloadType.TRAINING, ResourceProfile.GPU_ACCELERATED, [
        r'training', r'fine-?tun', r'instructlab', r'mlops',
    ]),
    (WorkloadType.RAG_PIPELINE, ResourceProfile.GPU_ACCELERATED, [
        r'\brag\b', r'retrieval.*augment', r'vector.*search', r'chatbot',
    ]),
    (WorkloadType.AGENT, ResourceProfile.SHARED_NAMESPACE, [
        r'agent.*ops', r'agentic', r'agent.*swarm', r'agent.*execution',
    ]),
    (WorkloadType.CPU_INFERENCE, ResourceProfile.SHARED_NAMESPACE, [
        r'genai', r'gen-ai', r'llama.*stack', r'openshift.*ai\b', r'rhoai',
        r'parasol', r'ai.*workshop', r'ai.*quickstart', r'ai-qs',
        r'sentiment', r'fraud.*detection', r'composer.*ai', r'ai.*factory',
        r'maas', r'llmaas', r'model.*service', r'ai.*lightning',
    ]),
    (WorkloadType.SECURITY, ResourceProfile.SHARED_NAMESPACE, [
        r'security', r'\bacs\b', r'rhacs', r'\bctf\b', r'devsecops', r'zero.*trust',
        r'breach', r'compliance', r'usbguard', r'selinux', r'openscap',
        r'hardened.*image', r'keylime', r'trusted.*pipeline', r'software.*supply',
    ]),
    (WorkloadType.EDGE, ResourceProfile.BARE_METAL, [
        r'\bedge\b', r'microshift', r'fleet.*management', r'edge.*manager',
        r'\bsno\b', r'single.*node',
    ]),
    (WorkloadType.PLATFORM_OPS, ResourceProfile.DEDICATED_CLUSTER, [
        r'gitops', r'argocd', r'service.*mesh', r'ossm', r'\bacm\b',
        r'platform.*eng', r'developer.*hub', r'\brhdh\b', r'lightspeed',
        r'hosted.*control', r'hcp', r'troubleshoot', r'must-gather',
        r'admin.*storage', r'perf.*scale', r'workload.*partition',
    ]),
    (WorkloadType.DEVELOPER, ResourceProfile.SHARED_NAMESPACE, [
        r'quarkus', r'camel', r'\beap\b', r'\bjava\b', r'jboss', r'developer.*suite',
        r'\bads\b', r'3scale', r'app.*platform', r'app.*connectivity',
        r'cloud.*native', r'service.*interconnect', r'integration',
    ]),
    (WorkloadType.INFRASTRUCTURE, ResourceProfile.VIRTUAL_MACHINE, [
        r'\brhel\b', r'satellite', r'image.*mode', r'imagebuilder', r'image.*builder',
        r'podman', r'container.*tools', r'buildah', r'crypto', r'tuned',
        r'admin.*101', r'leapp', r'in-place.*upgrade', r'insights',
        r'kernel.*patch', r'system.*roles', r'convert2rhel', r'epel',
        r'stratis', r'rpm', r'firewall', r'webconsole', r'pcp',
        r'session.*recording', r'sql.*server',
    ]),
    (WorkloadType.CLOUD_ENV, ResourceProfile.CLOUD_INSTANCE, [
        r'\brosa\b', r'\baro\b', r'\bgcp\b', r'azure', r'\baws\b',
        r'\bibm\b', r'open.*environment', r'cloud.*platform',
    ]),
    (WorkloadType.SANDBOX, ResourceProfile.MINIMAL, [
        r'sandbox', r'blank.*environment', r'dev.*sandbox', r'open.*environ',
        r'base.*rhel', r'base.*rhoai',
    ]),
    (WorkloadType.WORKSHOP, ResourceProfile.SHARED_NAMESPACE, [
        r'workshop', r'getting.*started', r'roadshow', r'bootcamp',
        r'hands.*on', r'lab.*developer', r'intro.*to\b',
    ]),
]


class WorkloadClassifier:

    def classify(self, catalog_item: CatalogItem, request: LabRequest) -> WorkloadProfile:
        caps = set(catalog_item.required_capabilities)
        hw = catalog_item.default_hardware_profile or ""
        meta = catalog_item.metadata or {}

        if meta.get("cpu_only"):
            return WorkloadProfile(
                workload_type=WorkloadType.CPU_INFERENCE, resource_profile=ResourceProfile.SHARED_NAMESPACE,
                compute_intensity="medium", memory_intensity="low", gpu_required=False,
                confidence=0.9, classification_source="catalog_metadata",
            )

        if hw == "mixed-overdrive" and len(caps) >= 3:
            return WorkloadProfile(
                workload_type=WorkloadType.MIXED, resource_profile=ResourceProfile.GPU_ACCELERATED,
                compute_intensity="high", memory_intensity="high", gpu_required=True, gpu_mode="endpoint",
                confidence=0.8, classification_source="catalog_metadata",
            )

        if "gaudi_direct" in caps:
            return WorkloadProfile(
                workload_type=WorkloadType.TRAINING, resource_profile=ResourceProfile.GPU_ACCELERATED,
                compute_intensity="high", memory_intensity="high", gpu_required=True, gpu_mode="direct",
                io_pattern="batch", confidence=0.9, classification_source="catalog_metadata",
            )

        if "vector_db" in caps:
            return WorkloadProfile(
                workload_type=WorkloadType.RAG_PIPELINE, resource_profile=ResourceProfile.GPU_ACCELERATED,
                compute_intensity="medium", memory_intensity="high",
                gpu_required="model_endpoint" in caps, gpu_mode="endpoint" if "model_endpoint" in caps else "none",
                confidence=0.9, classification_source="catalog_metadata",
            )

        if hw == "gaudi-endpoint" or "model_endpoint" in caps:
            return WorkloadProfile(
                workload_type=WorkloadType.GPU_INFERENCE, resource_profile=ResourceProfile.GPU_ACCELERATED,
                compute_intensity="high", memory_intensity="medium", gpu_required=True, gpu_mode="endpoint",
                confidence=0.7, classification_source="catalog_metadata",
            )

        if hw == "gaudi-direct":
            return WorkloadProfile(
                workload_type=WorkloadType.TRAINING, resource_profile=ResourceProfile.GPU_ACCELERATED,
                compute_intensity="high", memory_intensity="high", gpu_required=True, gpu_mode="direct",
                io_pattern="batch", confidence=0.7, classification_source="rules",
            )

        result = self._classify_by_name(catalog_item)
        if result:
            return result

        quota = catalog_item.default_quota_profile or ""
        if hw == "xeon-basic" and quota == "small":
            return WorkloadProfile(
                workload_type=WorkloadType.LIGHTWEIGHT, resource_profile=ResourceProfile.MINIMAL,
                compute_intensity="low", memory_intensity="low",
                confidence=0.6, classification_source="rules",
            )

        return WorkloadProfile(
            workload_type=WorkloadType.WORKSHOP, resource_profile=ResourceProfile.SHARED_NAMESPACE,
            compute_intensity="medium", memory_intensity="medium",
            confidence=0.3, classification_source="name_analysis",
        )

    def _classify_by_name(self, catalog_item: CatalogItem) -> Optional[WorkloadProfile]:
        name = catalog_item.catalog_item_id.lower()
        display = (catalog_item.display_name or "").lower()
        text = f"{name} {display}"

        for wtype, rprofile, patterns in NAME_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, text):
                    compute = "high" if wtype in (WorkloadType.TRAINING, WorkloadType.GPU_INFERENCE) else "medium"
                    memory = "high" if wtype in (WorkloadType.TRAINING, WorkloadType.RAG_PIPELINE, WorkloadType.VIRTUALIZATION) else "medium"
                    gpu = wtype in (WorkloadType.GPU_INFERENCE, WorkloadType.TRAINING, WorkloadType.RAG_PIPELINE)
                    return WorkloadProfile(
                        workload_type=wtype, resource_profile=rprofile,
                        compute_intensity=compute, memory_intensity=memory,
                        gpu_required=gpu, gpu_mode="endpoint" if gpu else "none",
                        confidence=0.7, classification_source="name_analysis",
                    )
        return None

    def match_hardware(self, profile: WorkloadProfile) -> List[HardwareMatch]:
        scores = WORKLOAD_HARDWARE_SCORES.get(profile.workload_type, DEFAULT_SCORES)

        matches = []
        for hw in HARDWARE_PROFILES:
            base_score = scores.get(hw, 30)
            reasons = []

            if profile.gpu_required and hw in ("gaudi-endpoint", "gaudi-direct", "mixed-overdrive"):
                reasons.append("GPU capability available")
            elif not profile.gpu_required and hw in ("xeon-basic", "xeon6"):
                reasons.append("CPU-only matches workload")

            if profile.workload_type == WorkloadType.VIRTUALIZATION:
                reasons.append("virtualization workload")
            elif profile.workload_type == WorkloadType.AUTOMATION:
                reasons.append("automation workload")
            elif profile.workload_type == WorkloadType.INFRASTRUCTURE:
                reasons.append("infrastructure management")

            quota = self.right_size_quota(profile, None)
            matches.append(HardwareMatch(
                hardware_profile=hw, score=float(base_score),
                reasons=reasons or [f"{profile.workload_type.value} workload"],
                right_sized_quota=quota,
            ))

        matches.sort(key=lambda m: -m.score)
        return matches

    def right_size_quota(self, profile: WorkloadProfile, catalog_item: Optional[CatalogItem]) -> str:
        if profile.gpu_required and profile.compute_intensity == "high":
            return "large"
        key = (profile.compute_intensity, profile.memory_intensity)
        return INTENSITY_TO_QUOTA.get(key, "standard")
