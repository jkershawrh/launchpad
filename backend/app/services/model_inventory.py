from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx


DEFAULT_MODEL_PORTFOLIO: List[Dict[str, str]] = [
    {"id": "smollm2-360m", "display_name": "SmolLM2 360M", "namespace": "intel-inference", "workload": "llama-smollm2-360m", "hardware": "Intel Xeon", "use_case": "Fast lightweight inference"},
    {"id": "smollm3-3b", "display_name": "SmolLM3 3B", "namespace": "intel-inference", "workload": "llama-smollm3-3b", "hardware": "Intel Xeon", "use_case": "Efficient instruction model"},
    {"id": "qwen36-moe", "display_name": "Qwen 35B MoE", "namespace": "intel-inference", "workload": "llama-qwen36-moe", "hardware": "Intel Gaudi", "use_case": "Reasoning and agents"},
    {"id": "llama31-8b-w8a8", "display_name": "Llama 3.1 8B W8A8", "namespace": "rhoai-learning", "workload": "llama31-8b-w8a8-predictor", "hardware": "Intel Gaudi", "use_case": "General instruction"},
    {"id": "granite-2b", "display_name": "Granite 2B", "namespace": "fleet-llm-d", "workload": "ovms-granite-2b", "hardware": "Intel Xeon", "use_case": "Enterprise AI"},
    {"id": "gemma-4-e4b", "display_name": "Gemma E4B Benchmark", "namespace": "intel-inference", "workload": "bench-model", "hardware": "Intel Gaudi", "use_case": "Performance benchmark"},
    {"id": "gemma3-4b", "display_name": "Gemma 3 4B", "namespace": "intel-inference", "workload": "llama-gemma3-4b", "hardware": "Intel Gaudi", "use_case": "Multimodal and general AI"},
    {"id": "granite-3b", "display_name": "Granite 3B", "namespace": "intel-inference", "workload": "llama-granite-3b", "hardware": "Intel Gaudi", "use_case": "Enterprise AI"},
    {"id": "llama32-1b", "display_name": "Llama 3.2 1B", "namespace": "intel-inference", "workload": "llama-llama32-1b", "hardware": "Intel Gaudi", "use_case": "Small language model"},
    {"id": "phi4-mini", "display_name": "Phi-4 Mini", "namespace": "intel-inference", "workload": "llama-phi4-mini", "hardware": "Intel Gaudi", "use_case": "Compact reasoning"},
]


def _apps_api():
    from kubernetes import client, config
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()
    return client.AppsV1Api()


def _exposed_models(api_base: str, api_key: str) -> set[str]:
    if not api_base:
        return set()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = httpx.get(f"{api_base.rstrip('/')}/v1/models", headers=headers, timeout=5)
    response.raise_for_status()
    return {item["id"] for item in response.json().get("data", []) if item.get("id")}


def get_model_inventory(
    portfolio: List[Dict[str, str]] | None = None,
    litellm_base: str | None = None,
    litellm_key: str | None = None,
) -> Dict[str, Any]:
    models = portfolio or DEFAULT_MODEL_PORTFOLIO
    try:
        exposed = _exposed_models(litellm_base if litellm_base is not None else os.getenv("LITELLM_API_BASE", ""), litellm_key if litellm_key is not None else os.getenv("LITELLM_API_KEY", ""))
    except Exception:
        exposed = set()

    apps = _apps_api()
    inventory = []
    for definition in models:
        desired = ready = 0
        exists = True
        try:
            deployment = apps.read_namespaced_deployment(definition["workload"], definition["namespace"])
            desired = deployment.spec.replicas or 0
            ready = deployment.status.ready_replicas or 0
        except Exception:
            exists = False

        is_exposed = definition["id"] in exposed
        if not exists:
            status = "missing"
        elif desired == 0:
            status = "stopped"
        elif ready < desired:
            status = "starting"
        elif not is_exposed:
            status = "running_not_exposed"
        else:
            status = "healthy"
        inventory.append({**definition, "desired_replicas": desired, "ready_replicas": ready, "litellm_exposed": is_exposed, "status": status})

    return {
        "summary": {
            "configured": len(inventory),
            "running": sum(1 for model in inventory if model["ready_replicas"] > 0),
            "exposed": sum(1 for model in inventory if model["litellm_exposed"]),
            "healthy": sum(1 for model in inventory if model["status"] == "healthy"),
        },
        "models": inventory,
    }
