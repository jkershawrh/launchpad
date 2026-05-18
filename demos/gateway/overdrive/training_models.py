"""Training demo models — profiles, runs, and serving candidates."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


MODEL_PROFILES = {
    "qwen_2_5_7b": {"family": "Qwen", "name": "Qwen2.5-7B", "params_b": 7, "task": "incident RCA / operations assistant", "training_lane": "gaudi_overdrive", "serving_lane": "gaudi_overdrive"},
    "qwen_2_5_coder_7b": {"family": "Qwen Coder", "name": "Qwen2.5-Coder-7B", "params_b": 7, "task": "build failure explanation / code summary", "training_lane": "gaudi_overdrive", "serving_lane": "gaudi_overdrive"},
    "qwen_2_5_vl_7b": {"family": "Qwen VL", "name": "Qwen2.5-VL-7B", "params_b": 7, "task": "dashboard screenshot interpretation / multimodal", "training_lane": "gaudi_overdrive", "serving_lane": "gaudi_overdrive"},
    "llama_3_1_8b": {"family": "Llama", "name": "Llama-3.1-8B", "params_b": 8, "task": "incident RCA / platform assistant", "training_lane": "gaudi_overdrive", "serving_lane": "gaudi_overdrive"},
    "granite_ops_model": {"family": "Granite", "name": "Granite-Ops", "params_b": 3, "task": "OpenShift troubleshooting / enterprise assistant", "training_lane": "gaudi_overdrive", "serving_lane": "gaudi_overdrive"},
    "phi_small_utility": {"family": "Phi", "name": "Phi-Small", "params_b": 1.5, "task": "lightweight classification / route helper", "training_lane": "xeon_performance", "serving_lane": "xeon_performance"},
}

DATASET_PROFILES = {
    "synthetic_incident_rca_v1": {"task_type": "incident_rca", "modality": "text", "sample_count": 1000, "train_count": 800, "eval_count": 200, "synthetic": True, "description": "Synthetic incident alerts, logs, service metadata, and expected RCA summaries."},
    "synthetic_openshift_troubleshooting_v1": {"task_type": "openshift_troubleshooting", "modality": "text", "sample_count": 500, "train_count": 400, "eval_count": 100, "synthetic": True, "description": "OpenShift error messages, oc describe/events/logs snippets, and expected explanations."},
    "synthetic_dashboard_vision_v1": {"task_type": "dashboard_vision", "modality": "image", "sample_count": 300, "train_count": 240, "eval_count": 60, "synthetic": True, "description": "Dashboard screenshot metadata, chart descriptions, visible symptoms, and expected summaries."},
    "synthetic_code_failure_v1": {"task_type": "code_failure", "modality": "text", "sample_count": 400, "train_count": 320, "eval_count": 80, "synthetic": True, "description": "Build/test failures, stack traces, code snippets, and expected fix explanations."},
    "synthetic_small_classifier_v1": {"task_type": "small_classifier", "modality": "text", "sample_count": 2000, "train_count": 1600, "eval_count": 400, "synthetic": True, "description": "Request metadata, task types, expected route class, and priority class for Xeon-side utility model."},
}

TRAINING_TASKS = {
    "incident_rca_finetune": {"model_profiles": ["qwen_2_5_7b", "llama_3_1_8b"], "datasets": ["synthetic_incident_rca_v1"]},
    "openshift_troubleshooting_finetune": {"model_profiles": ["granite_ops_model", "llama_3_1_8b"], "datasets": ["synthetic_openshift_troubleshooting_v1"]},
    "dashboard_vision_finetune": {"model_profiles": ["qwen_2_5_vl_7b"], "datasets": ["synthetic_dashboard_vision_v1"]},
    "code_failure_finetune": {"model_profiles": ["qwen_2_5_coder_7b"], "datasets": ["synthetic_code_failure_v1"]},
    "small_classifier_tune": {"model_profiles": ["phi_small_utility"], "datasets": ["synthetic_small_classifier_v1"]},
}

VALID_TRAINING_MODES = {"mock_lora", "mock_sft", "real_lora", "real_sft", "real_qlora", "real_adapter_merge"}
VALID_STATUSES = {"created", "running", "completed", "failed", "skipped", "simulated"}
VALID_HARDWARE_LANES = {"xeon_eco", "xeon_performance", "gaudi_overdrive", "unknown"}


@dataclass
class TrainingRun:
    training_run_id: str
    demo_task: str
    model_profile_id: str
    base_model_name: str
    dataset_id: str
    dataset_version: str = "v1"
    training_mode: str = "mock_lora"
    hardware_lane: str = "gaudi_overdrive"
    status: str = "created"
    started_at: str = ""
    completed_at: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    loss_curve: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServingCandidate:
    serving_candidate_id: str
    training_run_id: str
    model_profile_id: str
    artifact_ref: str
    target_lane: str
    status: str = "created"
    endpoint_ref: str = ""
    created_at: str = ""


def list_model_profiles() -> list[dict]:
    return [{"id": k, **v} for k, v in MODEL_PROFILES.items()]


def list_dataset_profiles() -> list[dict]:
    return [{"id": k, **v} for k, v in DATASET_PROFILES.items()]


DATASET_SAMPLES = {
    "synthetic_incident_rca_v1": [
        {
            "input": "Alerts: ['api-gateway p95 latency above threshold', 'checkout-service error rate elevated']\nLogs: ['timeout connecting to payment-service', 'connection pool exhausted']\nService: checkout-service → payment-service",
            "base_output": "There appears to be an issue with the checkout service. The latency is high and there are errors. You should investigate the service.",
            "tuned_output": "Checkout latency and errors are caused by payment-service connection pool exhaustion. The payment-service is saturated — incoming connections exceed the pool limit of 50. Immediate action: increase connection pool size to 100 and add circuit breaker. Root cause: payment-service was not scaled during the recent traffic increase.",
        },
        {
            "input": "Alerts: ['gaudi-worker-01 GPU memory utilization 97%', 'inference-gateway p99 > 10s']\nLogs: ['HBM allocation failed for batch-job-7842', 'fallback routing activated']\nService: inference-gateway → gaudi-inference",
            "base_output": "The GPU memory is full and inference is slow. Check the GPU usage.",
            "tuned_output": "Gaudi HBM exhaustion caused by unthrottled batch-job-7842 consuming 94GB of 96GB available. The routing engine activated fallback to Xeon 6 Performance lane, causing p99 latency spike from 200ms to 10s. Fix: terminate batch-job-7842, add habana.ai/gaudi resource limits to batch workload manifests, implement token budget admission controller for the Gaudi lane.",
        },
    ],
    "synthetic_openshift_troubleshooting_v1": [
        {
            "input": "Error: CrashLoopBackOff on pod vllm-gaudi-0 in namespace gaudi-inference\noc describe: Back-off restarting failed container, Exit code 137 (OOMKilled)",
            "base_output": "The pod is crashing. Try restarting it or checking the logs.",
            "tuned_output": "Pod vllm-gaudi-0 is being OOMKilled (exit 137) — the container memory limit is too low for the model being served. For a 17B parameter model on Gaudi, set memory request to 32Gi and limit to 64Gi. Check: `oc get pod vllm-gaudi-0 -o jsonpath='{.spec.containers[0].resources}'`. Also verify the model fits in Gaudi HBM: `hl-smi` should show sufficient free memory.",
        },
    ],
    "synthetic_dashboard_vision_v1": [
        {
            "input": "[Dashboard screenshot showing latency spike from 200ms to 4,500ms with correlated error rate increase from 0.1% to 3.2%]",
            "base_output": "The chart shows some metrics changing over time.",
            "tuned_output": "This Grafana dashboard shows a critical latency degradation event starting at 14:23 UTC. P99 latency increased 22x (200ms → 4,500ms) over 15 minutes. The error rate panel shows a correlated increase from 0.1% to 3.2%, with HTTP 502 errors concentrated on the /v1/route endpoint. The service status panel shows 2 of 5 inference pods unhealthy. This pattern is consistent with a Gaudi accelerator failure causing fallback routing overload on Xeon 6.",
        },
    ],
}

TRAINING_METHOD_INFO = {
    "lora": {"name": "LoRA", "full_name": "Low-Rank Adaptation", "trainable_pct": 0.5, "memory_gb": 16, "time_factor": 1, "quality": "Near-full", "description": "Trains small adapter matrices (~35M params for 7B model). Fast, memory-efficient, production-ready. The adapter merges with the base model at serving time."},
    "sft": {"name": "Full SFT", "full_name": "Supervised Fine-Tuning", "trainable_pct": 100, "memory_gb": 60, "time_factor": 6, "quality": "Highest", "description": "Updates all model weights. Maximum quality but requires full model in memory. Best for large datasets and research. Produces a complete model checkpoint."},
    "qlora": {"name": "QLoRA", "full_name": "Quantized LoRA", "trainable_pct": 0.5, "memory_gb": 8, "time_factor": 1.2, "quality": "Good", "description": "LoRA on a 4-bit quantized base model. Fits in less memory with minimal quality loss. Good for memory-constrained environments or edge deployment."},
}

HARDWARE_TRAINING_BENCHMARKS = {
    "xeon6": {
        "name": "Intel Xeon 6",
        "memory": "256GB DDR5",
        "lora_7b_time": "~4 hours",
        "sft_7b_time": "Not viable",
        "best_for": "Small model training (≤3B), inference serving, evaluation",
        "advantage": "No GPU required — train lightweight classifiers and utility models on the same hardware that serves them",
    },
    "gaudi": {
        "name": "Intel Gaudi 2",
        "memory": "96GB HBM2E",
        "lora_7b_time": "~20 minutes",
        "sft_7b_time": "~2 hours",
        "best_for": "All serious training — LoRA, SFT, QLoRA for 7B-70B models",
        "advantage": "High-bandwidth memory enables large batch sizes and fast gradient computation. 24 tensor cores optimized for training throughput.",
    },
}


def list_training_tasks() -> list[dict]:
    return [{"id": k, **v} for k, v in TRAINING_TASKS.items()]
