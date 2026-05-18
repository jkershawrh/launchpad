"""Deterministic workload batch generation from profile + mode + seed."""

import random
from .models import InferenceRequest
from .power_modes import get_mode_config
from .workload_profiles import PROFILES

MULTIMODAL_DEMO_ASSETS = {
    "screenshot": [
        {"url": "/demo-assets/dashboard-latency-spike.svg", "title": "Inference Gateway Latency Spike", "description": "Grafana dashboard showing p99 latency spike from 200ms to 4,500ms with correlated error rate increase."},
        {"url": "/demo-assets/error-rate-dashboard.svg", "title": "Error Rate Monitor", "description": "HTTP 502 error tracking with affected services and incident timeline."},
        {"url": "/demo-assets/chart-throughput-comparison.svg", "title": "Throughput vs Utilization", "description": "24-hour throughput chart showing Gaudi utilization correlation with request volume."},
    ],
    "diagram": [
        {"url": "/demo-assets/architecture-dual-path.svg", "title": "Dual-Path Routing Architecture", "description": "Three-lane routing diagram: Eco (Xeon 6), Performance (Xeon 6 + AMX), Overdrive (Gaudi)."},
    ],
    "image": [
        {"url": "/demo-assets/gaudi-accelerator-card.svg", "title": "Intel Gaudi 2 Accelerator", "description": "Intel Gaudi 2 HL-225 PCIe card with 96GB HBM2E and 24 Tensor Cores."},
        {"url": "/demo-assets/server-rack-xeon6.svg", "title": "2U Rack Server — Xeon 6 + Gaudi", "description": "Rack-mounted servers with CPU worker node and Gaudi worker node."},
    ],
    "document": [
        {"url": "/demo-assets/architecture-dual-path.svg", "title": "Platform Architecture Document", "description": "15-page technical architecture document with embedded diagrams."},
    ],
    "mixed": [
        {"url": "/demo-assets/dashboard-latency-spike.svg", "title": "Multi-Source Incident Evidence", "description": "Dashboard screenshots combined with log analysis for incident synthesis."},
    ],
}

MULTIMODAL_IMAGE_FIXTURES = [
    "fixtures/multimodal/images/dashboard-latency-spike-001.json",
    "fixtures/multimodal/images/dashboard-kafka-lag-001.json",
    "fixtures/multimodal/images/diagram-inference-platform-001.json",
    "fixtures/multimodal/images/chart-throughput-001.json",
    "fixtures/multimodal/images/grafana-error-rate-001.json",
    "fixtures/multimodal/images/architecture-dual-path-001.json",
]

MULTIMODAL_DOC_FIXTURES = [
    "fixtures/multimodal/documents/incident-report-page-001.json",
    "fixtures/multimodal/documents/architecture-doc-page-001.json",
    "fixtures/multimodal/documents/deployment-guide-page-001.json",
]

LATENCY_DEFAULTS = {
    "classification": 8000,
    "embedding": 5000,
    "rerank": 5000,
    "short_summary": 8000,
    "long_summary": 5000,
    "incident_rca": 5000,
    "batch_summary": 10000,
    "rag_question": 5000,
    "document_summary": 5000,
    "code_summary": 5000,
    "image_classification": 8000,
    "screenshot_classification": 8000,
    "image_text_embedding": 5000,
    "visual_similarity": 5000,
    "ocr_layout_extract": 5000,
    "screenshot_summary": 5000,
    "chart_interpretation": 5000,
    "diagram_explanation": 5000,
    "document_visual_summary": 5000,
    "visual_rag_question": 5000,
    "multimodal_incident_summary": 5000,
    "multimodal_rca": 5000,
    "image_to_manual": 10000,
}


def generate_workload(
    profile: str,
    mode: str,
    seed: int,
    count: int = None,
    concurrency: int = None,
) -> list[InferenceRequest]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")

    profile_data = PROFILES[profile]
    cfg = get_mode_config(mode, count=count, concurrency=concurrency)
    total = cfg["count"]
    mix = profile_data["task_mix"]
    total_weight = sum(e["weight"] for e in mix)

    rng = random.Random(seed)
    requests = []

    for i in range(total):
        roll = rng.random() * total_weight
        cumulative = 0
        entry = mix[0]
        for e in mix:
            cumulative += e["weight"]
            if roll < cumulative:
                entry = e
                break

        low, high = entry["token_range"]
        token_estimate = rng.randint(low, high)

        prompts_for_task = profile_data.get("prompts", {}).get(entry["task_type"], [])
        prompt = prompts_for_task[rng.randint(0, len(prompts_for_task) - 1)] if prompts_for_task else ""

        modality = entry.get("modality", "text")
        image_count = 0
        page_count = 0
        image_ref = ""
        document_ref = ""

        icr = entry.get("image_count_range")
        if icr:
            image_count = rng.randint(icr[0], icr[1])
            image_ref = MULTIMODAL_IMAGE_FIXTURES[rng.randint(0, len(MULTIMODAL_IMAGE_FIXTURES) - 1)]

        pcr = entry.get("page_count_range")
        if pcr:
            page_count = rng.randint(pcr[0], pcr[1])
            document_ref = MULTIMODAL_DOC_FIXTURES[rng.randint(0, len(MULTIMODAL_DOC_FIXTURES) - 1)]

        metadata = {}
        if modality in MULTIMODAL_DEMO_ASSETS and MULTIMODAL_DEMO_ASSETS[modality]:
            assets = MULTIMODAL_DEMO_ASSETS[modality]
            asset = assets[rng.randint(0, len(assets) - 1)]
            metadata["image_url"] = asset["url"]
            metadata["image_title"] = asset["title"]
            metadata["image_description"] = asset["description"]

        requests.append(InferenceRequest(
            request_id=f"wl-{seed}-{i:05d}",
            task_type=entry["task_type"],
            priority=entry["priority"],
            token_estimate=token_estimate,
            latency_target_ms=LATENCY_DEFAULTS.get(entry["task_type"], 5000),
            prompt=prompt,
            modality=modality,
            image_ref=image_ref,
            document_ref=document_ref,
            image_count=image_count,
            page_count=page_count,
            metadata=metadata,
        ))

    return requests
