#!/usr/bin/env python3
"""
Enterprise RAG Demo — Intel-Red Hat AI Partner Platform

Demonstrates the full inference continuum:
  1. Embed query on Xeon 6 (OpenVINO, AMX-accelerated)
  2. Vector search (simulated — would use a real vector DB)
  3. Rerank candidates on Xeon 6 (OpenVINO, cross-encoder)
  4. Generate answer on Gaudi (vLLM, large LLM)

Every step routes through the inference gateway.
The response includes a full routing trace showing
which hardware handled each stage and why.
"""

import os
import time
import json
import httpx
import argparse
import sys

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
MOCK_MODE = False

SAMPLE_DOCS = [
    {"id": 1, "text": "OpenShift AI provides a platform for training and serving ML models on Kubernetes with support for GPUs and accelerators."},
    {"id": 2, "text": "Intel Xeon 6 processors include AMX (Advanced Matrix Extensions) which accelerate INT8 and BF16 inference workloads natively on CPU."},
    {"id": 3, "text": "Intel Gaudi accelerators provide high-bandwidth memory and tensor processing cores optimized for transformer model inference."},
    {"id": 4, "text": "KServe enables serverless model serving on Kubernetes with autoscaling, canary deployments, and multi-framework support."},
    {"id": 5, "text": "The vLLM inference engine uses PagedAttention for efficient memory management during LLM serving."},
    {"id": 6, "text": "OpenVINO Model Server supports ONNX and OpenVINO IR model formats with automatic hardware optimization."},
    {"id": 7, "text": "Red Hat Enterprise Linux provides the foundation for OpenShift, offering security, stability, and long-term support."},
    {"id": 8, "text": "Model quantization to INT8 or BF16 enables 2-4x inference speedup on Intel hardware with minimal accuracy loss."},
]

MOCK_RESPONSES = {
    "embeddings": {"routing": {"selected_backend": "openvino-cpu", "accelerator": "xeon6", "reason": "Embeddings are compute-bound, AMX-accelerated on Xeon 6", "latency_ms": 4.2, "cost_estimate_per_1k_tokens": 0.001, "task": "embeddings"}, "result": {"data": [{"embedding": [0.1]*384}]}},
    "reranking": {"routing": {"selected_backend": "openvino-cpu", "accelerator": "xeon6", "reason": "Reranking is latency-sensitive, CPU avoids GPU queue contention", "latency_ms": 8.1, "cost_estimate_per_1k_tokens": 0.001, "task": "reranking"}, "result": {"scores": [0.9, 0.7, 0.3]}},
    "completion": {"routing": {"selected_backend": "vllm-gaudi", "accelerator": "gaudi", "reason": "Large models (> 3B) need Gaudi HBM and tensor acceleration", "latency_ms": 1200, "cost_estimate_per_1k_tokens": 0.008, "task": "completion"}, "result": {"choices": [{"text": "Intel Xeon 6 processors accelerate AI inference through Advanced Matrix Extensions (AMX), which provide hardware-level acceleration for INT8 and BF16 matrix operations. This enables 2-4x speedup for inference workloads on CPU without requiring dedicated GPU hardware."}]}},
}


def call_gateway(task: str, **kwargs) -> dict:
    if MOCK_MODE:
        time.sleep(0.05)
        return MOCK_RESPONSES.get(task, MOCK_RESPONSES["completion"])
    try:
        payload = {"task": task, **kwargs}
        resp = httpx.post(f"{GATEWAY_URL}/v1/route", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        print(f"  ERROR: Gateway unreachable at {GATEWAY_URL}", file=sys.stderr)
        print(f"  Run with --mock for offline demo", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"  ERROR: Gateway returned {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.TimeoutException:
        print(f"  ERROR: Gateway timed out", file=sys.stderr)
        sys.exit(1)


def step_embed(query: str) -> dict:
    result = call_gateway("embeddings", text=query)
    return {
        "step": "embed_query",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "reason": result["routing"]["reason"],
        "latency_ms": result["routing"]["latency_ms"],
    }


def step_search(query: str) -> list:
    query_words = set(query.lower().split())
    scored = []
    for doc in SAMPLE_DOCS:
        doc_words = set(doc["text"].lower().split())
        overlap = len(query_words & doc_words)
        scored.append({"doc": doc, "score": overlap})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return [s["doc"] for s in scored[:4]]


def step_rerank(query: str, candidates: list) -> dict:
    texts = [doc["text"] for doc in candidates]
    result = call_gateway("reranking", text=query, texts=texts)
    return {
        "step": "rerank",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "reason": result["routing"]["reason"],
        "latency_ms": result["routing"]["latency_ms"],
        "top_docs": candidates[:3],
    }


def step_generate(query: str, context_docs: list) -> dict:
    context = "\n".join([f"- {doc['text']}" for doc in context_docs])
    prompt = f"Based on the following context, answer the question.\n\nContext:\n{context}\n\nQuestion: {query}\n\nAnswer:"
    result = call_gateway("completion", prompt=prompt, model_size_b=7, max_tokens=200, temperature=0.3)
    error = result.get("error")
    if error:
        print(f"  WARNING: Generation error: {error}", file=sys.stderr)
    choices = result.get("result", {}).get("choices", [{}])
    answer = choices[0].get("text", "") if choices else ""
    return {
        "step": "generate",
        "backend": result["routing"]["selected_backend"],
        "accelerator": result["routing"]["accelerator"],
        "reason": result["routing"]["reason"],
        "latency_ms": result["routing"]["latency_ms"],
        "answer": answer,
        "cost_per_1k": result["routing"]["cost_estimate_per_1k_tokens"],
    }


def run_rag(query: str, verbose: bool = False):
    print(f"\n{'='*60}")
    print(f"Enterprise RAG Demo" + (" [MOCK MODE]" if MOCK_MODE else ""))
    print(f"{'='*60}")
    print(f"Query: {query}\n")

    trace = []
    total_start = time.time()

    print("[1/4] Embedding query on Xeon 6 (OpenVINO)...")
    embed_result = step_embed(query)
    trace.append(embed_result)
    print(f"      -> {embed_result['backend']} ({embed_result['latency_ms']:.0f}ms)")

    print("[2/4] Searching knowledge base...")
    candidates = step_search(query)
    trace.append({"step": "vector_search", "backend": "local", "accelerator": "local", "candidates": len(candidates)})
    print(f"      -> {len(candidates)} candidates found")

    print("[3/4] Reranking on Xeon 6 (OpenVINO cross-encoder)...")
    rerank_result = step_rerank(query, candidates)
    trace.append(rerank_result)
    print(f"      -> {rerank_result['backend']} ({rerank_result['latency_ms']:.0f}ms)")

    print("[4/4] Generating answer on Gaudi (vLLM)...")
    gen_result = step_generate(query, rerank_result["top_docs"])
    trace.append(gen_result)
    print(f"      -> {gen_result['backend']} ({gen_result['latency_ms']:.0f}ms)")

    total_ms = (time.time() - total_start) * 1000

    print(f"\n{'='*60}")
    print(f"Answer: {gen_result.get('answer', '[no answer generated]')}")
    print(f"{'='*60}")
    print(f"\nRouting Trace:")
    print(f"  Step 1 (embed):    {trace[0]['accelerator']:>8}  {trace[0]['backend']}")
    print(f"  Step 2 (search):   {'local':>8}  in-memory")
    print(f"  Step 3 (rerank):   {trace[2]['accelerator']:>8}  {trace[2]['backend']}")
    print(f"  Step 4 (generate): {trace[3]['accelerator']:>8}  {trace[3]['backend']}")
    print(f"\n  Total: {total_ms:.0f}ms | Xeon 6 handled 3/4 steps | Gaudi handled generation")

    if verbose:
        print(f"\nFull trace:")
        print(json.dumps(trace, indent=2, default=str))

    return {"answer": gen_result.get("answer", ""), "trace": trace, "total_ms": total_ms}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enterprise RAG Demo")
    parser.add_argument("--query", default="How does Intel Xeon 6 accelerate AI inference?")
    parser.add_argument("--gateway", default=None, help="Gateway URL")
    parser.add_argument("--mock", action="store_true", help="Run without gateway (simulated responses)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.gateway:
        GATEWAY_URL = args.gateway
    MOCK_MODE = args.mock

    result = run_rag(args.query, verbose=args.verbose)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
