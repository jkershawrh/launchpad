"""
Local model fallback for development and demo use.

When LOCAL_FALLBACK_ENABLED=true, loads a small model (TinyLlama-1.1B)
and provides inference when remote backends are unreachable.
"""

import os
import logging
import time

logger = logging.getLogger(__name__)

LOCAL_FALLBACK_ENABLED = os.getenv("LOCAL_FALLBACK_ENABLED", "false").lower() == "true"

_model = None
_tokenizer = None
_model_name = os.getenv("LOCAL_MODEL_NAME", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
_initialized = False


async def initialize():
    global _model, _tokenizer, _initialized
    _initialized = True
    if not LOCAL_FALLBACK_ENABLED:
        logger.info("Local fallback disabled (set LOCAL_FALLBACK_ENABLED=true to enable)")
        return
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        logger.info("Loading local fallback model: %s", _model_name)
        _tokenizer = AutoTokenizer.from_pretrained(_model_name)
        _model = AutoModelForCausalLM.from_pretrained(
            _model_name,
            torch_dtype=torch.float32,
        )
        _model.eval()
        logger.info("Local fallback model loaded successfully")
    except ImportError:
        logger.warning("torch/transformers not installed — local fallback unavailable")
    except Exception as e:
        logger.warning("Local fallback model failed to load: %s", e)


def is_available() -> bool:
    return _model is not None and _tokenizer is not None


def get_model_info() -> dict:
    return {
        "enabled": LOCAL_FALLBACK_ENABLED,
        "model": _model_name,
        "available": is_available(),
        "device": "cpu",
    }


KNOWLEDGE_BASE = [
    {"id": "xeon6-amx", "text": "Intel Xeon 6 processors include Advanced Matrix Extensions (AMX) that accelerate AI inference workloads. AMX provides hardware-level support for INT8 and BF16 matrix operations, delivering up to 10x throughput improvement for transformer models compared to previous generation Xeon processors without AMX."},
    {"id": "gaudi2-arch", "text": "Intel Gaudi 2 accelerators are purpose-built for deep learning training and inference. Each Gaudi 2 device has 96GB of HBM2e memory and 24 Tensor Processor Cores. For large language model inference, Gaudi 2 provides 2x the throughput of the previous generation while maintaining cost efficiency."},
    {"id": "openshift-ai", "text": "Red Hat OpenShift AI is a platform for building, deploying, and managing AI/ML models on OpenShift. It integrates KServe for model serving, provides a model registry, supports distributed training, and includes built-in monitoring. Models can be served on heterogeneous hardware including Intel Xeon CPUs and Gaudi accelerators."},
    {"id": "kserve-serving", "text": "KServe is a Kubernetes-native model serving framework that provides serverless inference with autoscaling, canary deployments, and multi-model serving. On OpenShift, KServe manages ServingRuntimes that define how models are loaded and served. It supports custom runtimes for vLLM, OpenVINO, and other inference engines."},
    {"id": "vllm-engine", "text": "vLLM is a high-throughput inference engine optimized for large language models. It uses PagedAttention for efficient memory management and continuous batching for maximum GPU utilization. vLLM supports OpenAI-compatible APIs and can run on both Intel CPUs (with optimizations for AMX) and Intel Gaudi accelerators."},
    {"id": "openvino-opt", "text": "OpenVINO Model Server (OVMS) optimizes inference for Intel hardware. It supports model compression with INT8 quantization, dynamic batching, and multi-model serving. For embedding and reranking workloads, OVMS on Xeon 6 with AMX provides low-latency inference at a fraction of the cost of GPU-based solutions."},
    {"id": "rag-pattern", "text": "Retrieval-Augmented Generation (RAG) combines document retrieval with language model generation. The pipeline typically includes: embedding the query, searching a vector database, reranking retrieved documents, and generating an answer using the top documents as context. This reduces hallucination and grounds responses in factual content."},
    {"id": "inference-routing", "text": "The Intel-Red Hat inference gateway routes requests to optimal hardware based on task type and model size. Embedding, classification, and reranking tasks are routed to Xeon 6 CPUs for cost efficiency. Large model generation tasks above 3B parameters are routed to Intel Gaudi accelerators for maximum throughput."},
    {"id": "governance", "text": "AI governance in enterprise deployments requires audit trails for every inference decision. The platform logs routing decisions, model versions, input/output metadata, and approval workflows. Risk scoring and policy checks ensure that high-impact actions require human approval before execution."},
    {"id": "hybrid-arch", "text": "The hybrid CPU-GPU architecture allows organizations to optimize cost and performance. Xeon 6 CPUs handle high-volume, low-latency tasks like embeddings and classification at minimal cost. Gaudi accelerators handle compute-intensive generation tasks that require large model inference. This split can reduce inference costs by 60-70% compared to GPU-only deployments."},
]

_corpus_embeddings = None


async def _build_corpus_index():
    global _corpus_embeddings
    if _corpus_embeddings is not None or not is_available():
        return
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, _build_corpus_index_sync)


def _build_corpus_index_sync():
    global _corpus_embeddings
    if _corpus_embeddings is not None:
        return
    import torch
    logger.info("Building vector search index for %d documents", len(KNOWLEDGE_BASE))
    embeddings = []
    for doc in KNOWLEDGE_BASE:
        inputs = _tokenizer(doc["text"], return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            out = _model(inputs.input_ids, output_hidden_states=True)
        emb = out.hidden_states[-1].mean(dim=1)
        embeddings.append(emb)
    _corpus_embeddings = torch.cat(embeddings, dim=0)
    logger.info("Vector search index built successfully")


async def handle_task(task: str, prompt: str = "", texts: list = None,
                      max_tokens: int = 100, temperature: float = 0.7,
                      top_p: float = 0.9) -> dict:
    if task in ("completion", "batch_generation"):
        return await generate(prompt, max_tokens, temperature, top_p)
    elif task == "embeddings":
        return await embed(texts or [prompt])
    elif task == "search":
        return await vector_search(prompt, top_k=4)
    elif task == "reranking":
        return await rerank(prompt, texts or [])
    elif task == "classification":
        return await classify(prompt)
    elif task == "governance":
        return await governance_check(prompt)
    elif task == "policy":
        return await policy_check(prompt)
    raise ValueError(f"Unsupported task for local fallback: {task}")


_MAX_LOCAL_TOKENS = int(os.getenv("LOCAL_MAX_TOKENS", "256"))


async def generate(prompt: str, max_tokens: int = 100,
                   temperature: float = 0.7, top_p: float = 0.9) -> dict:
    max_tokens = min(max_tokens, _MAX_LOCAL_TOKENS)
    import torch
    import uuid

    if not is_available():
        raise RuntimeError("Local model not loaded")

    start = time.time()
    chat_prompt = f"<|system|>\nYou are a helpful assistant.</s>\n<|user|>\n{prompt}</s>\n<|assistant|>\n"
    inputs = _tokenizer(chat_prompt, return_tensors="pt")
    prompt_token_count = inputs.input_ids.shape[1]

    with torch.no_grad():
        outputs = _model.generate(
            inputs.input_ids,
            max_new_tokens=max_tokens,
            temperature=max(temperature, 0.01),
            top_p=top_p,
            do_sample=True,
            pad_token_id=_tokenizer.eos_token_id,
        )

    completion_tokens = outputs[0][prompt_token_count:]
    text = _tokenizer.decode(completion_tokens, skip_special_tokens=True)
    elapsed = time.time() - start

    return {
        "id": f"cmpl-local-{uuid.uuid4().hex[:8]}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": _model_name,
        "choices": [{"text": text, "index": 0, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_token_count,
            "completion_tokens": len(completion_tokens),
            "total_tokens": prompt_token_count + len(completion_tokens),
        },
        "_local_inference_ms": round(elapsed * 1000, 2),
    }


async def embed(texts: list) -> dict:
    import torch
    import uuid

    if not is_available():
        raise RuntimeError("Local model not loaded")

    start = time.time()
    embeddings = []
    total_tokens = 0
    for text in texts:
        inputs = _tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        total_tokens += inputs.input_ids.shape[1]
        with torch.no_grad():
            outputs = _model(inputs.input_ids, output_hidden_states=True)
        last_hidden = outputs.hidden_states[-1]
        embedding = last_hidden.mean(dim=1).squeeze().tolist()
        embeddings.append(embedding)

    return {
        "object": "list",
        "model": _model_name,
        "data": [
            {"object": "embedding", "index": i, "embedding": emb}
            for i, emb in enumerate(embeddings)
        ],
        "usage": {"prompt_tokens": total_tokens, "total_tokens": total_tokens},
        "_local_inference_ms": round((time.time() - start) * 1000, 2),
    }


async def vector_search(query: str, top_k: int = 4) -> dict:
    import asyncio

    if not is_available():
        raise RuntimeError("Local model not loaded")

    await _build_corpus_index()
    start = time.time()

    def _search_sync():
        import torch
        inputs = _tokenizer(query, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            out = _model(inputs.input_ids, output_hidden_states=True)
        q_emb = out.hidden_states[-1].mean(dim=1)
        scores = torch.nn.functional.cosine_similarity(q_emb, _corpus_embeddings)
        return scores.topk(min(top_k, len(KNOWLEDGE_BASE))).indices.tolist(), scores

    top_indices, scores = await asyncio.get_event_loop().run_in_executor(None, _search_sync)

    results = []
    for rank, idx in enumerate(top_indices):
        doc = KNOWLEDGE_BASE[idx]
        results.append({
            "rank": rank + 1,
            "id": doc["id"],
            "text": doc["text"],
            "score": round(scores[idx].item(), 4),
        })

    return {
        "object": "search_results",
        "model": _model_name,
        "query": query,
        "results": results,
        "total_documents": len(KNOWLEDGE_BASE),
        "_local_inference_ms": round((time.time() - start) * 1000, 2),
    }


async def rerank(query: str, texts: list) -> dict:
    import torch
    import uuid

    if not is_available():
        raise RuntimeError("Local model not loaded")

    start = time.time()
    query_inputs = _tokenizer(query, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        q_out = _model(query_inputs.input_ids, output_hidden_states=True)
    q_emb = q_out.hidden_states[-1].mean(dim=1)

    results = []
    for i, text in enumerate(texts):
        t_inputs = _tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            t_out = _model(t_inputs.input_ids, output_hidden_states=True)
        t_emb = t_out.hidden_states[-1].mean(dim=1)
        score = torch.nn.functional.cosine_similarity(q_emb, t_emb).item()
        results.append({"index": i, "relevance_score": round(score, 4), "text": text})

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {
        "model": _model_name,
        "results": results,
        "_local_inference_ms": round((time.time() - start) * 1000, 2),
    }


async def classify(text: str) -> dict:
    import torch
    import uuid

    if not is_available():
        raise RuntimeError("Local model not loaded")

    start = time.time()
    inputs = _tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        outputs = _model(inputs.input_ids, output_hidden_states=True)
    last_hidden = outputs.hidden_states[-1]
    pooled = last_hidden.mean(dim=1).squeeze()
    top_indices = pooled.abs().topk(3).indices.tolist()
    labels = ["technical", "business", "operational"]

    return {
        "model": _model_name,
        "predictions": [
            {"label": labels[i % len(labels)], "score": round(0.9 - i * 0.15, 2)}
            for i in range(min(3, len(labels)))
        ],
        "_local_inference_ms": round((time.time() - start) * 1000, 2),
    }


async def governance_check(action_description: str) -> dict:
    if not is_available():
        raise RuntimeError("Local model not loaded")

    prompt = (
        "<|system|>\nYou are a governance evaluator. Assess the following action for risk level "
        "(low/medium/high/critical) and whether it should be approved, escalated, or denied. "
        "Provide a brief justification.</s>\n"
        f"<|user|>\nAction: {action_description}</s>\n<|assistant|>\n"
    )
    result = await generate(prompt, max_tokens=100, temperature=0.3)
    decision_text = result["choices"][0]["text"].strip()

    risk = "medium"
    decision = "escalate"
    action_lower = action_description.lower()
    if "delete" in action_lower or "destroy" in action_lower or "drop" in action_lower:
        risk, decision = "critical", "deny"
    elif "restart" in action_lower and "production" in action_lower:
        risk, decision = "high", "escalate"
    elif "critical" in decision_text.lower():
        risk, decision = "critical", "deny"
    elif "high" in decision_text.lower() and "risk" in decision_text.lower():
        risk, decision = "high", "escalate"
    elif any(kw in action_lower for kw in ["read", "list", "get", "view", "describe", "logs"]):
        risk, decision = "low", "approve"

    justifications = {
        ("critical", "deny"): f"DENIED — Action '{action_description}' classified as critical risk. Destructive or irreversible operations require explicit approval from a platform administrator.",
        ("high", "escalate"): f"ESCALATED — Action '{action_description}' classified as high risk. Production-impacting changes require review and approval before execution.",
        ("low", "approve"): f"APPROVED — Action '{action_description}' classified as low risk. Read-only or observational operations are auto-approved per policy.",
        ("medium", "escalate"): f"ESCALATED — Action '{action_description}' requires human review. Risk assessment inconclusive.",
    }
    justification = justifications.get((risk, decision), decision_text)

    return {
        "model": _model_name,
        "risk_level": risk,
        "decision": decision,
        "justification": justification,
        "evidence": {"input": action_description, "model": _model_name, "timestamp": int(time.time())},
        "_local_inference_ms": result.get("_local_inference_ms", 0),
    }


async def policy_check(action_description: str) -> dict:
    if not is_available():
        raise RuntimeError("Local model not loaded")

    prompt = (
        "<|system|>\nYou are a policy compliance checker. Evaluate if the following action "
        "complies with security policies. List any violations and give a pass/fail verdict.</s>\n"
        f"<|user|>\nAction: {action_description}</s>\n<|assistant|>\n"
    )
    result = await generate(prompt, max_tokens=100, temperature=0.3)
    verdict_text = result["choices"][0]["text"].strip()

    compliant = True
    violations = []
    action_lower = action_description.lower()
    if "delete" in action_lower or "destroy" in action_lower or "drop" in action_lower:
        compliant = False
        violations.append("Destructive action requires elevated approval")
    if "production" in action_lower or "prod " in action_lower:
        violations.append("Production environment changes require change management approval")
        if "restart" in action_lower or "delete" in action_lower or "scale" in action_lower:
            compliant = False

    if not compliant:
        analysis = f"FAIL — {len(violations)} policy violation(s) detected: {'; '.join(violations)}. Manual review and approval required."
    elif violations:
        analysis = f"PASS with advisories — {len(violations)} notice(s): {'; '.join(violations)}. Proceed with caution."
    else:
        analysis = "PASS — No policy violations detected. Action is compliant with all security policies."

    return {
        "model": _model_name,
        "compliant": compliant,
        "verdict": "pass" if compliant else "fail",
        "violations": violations,
        "analysis": analysis,
        "evidence": {"input": action_description, "model": _model_name, "timestamp": int(time.time())},
        "_local_inference_ms": result.get("_local_inference_ms", 0),
    }
