# Enterprise RAG Demo

**Run enterprise RAG on Intel hardware with Red Hat as the operating platform.**

## What This Shows Partners

A question-answering pipeline where each stage routes to the optimal Intel hardware:

```
Question: "How does Xeon 6 accelerate AI?"
    |
    v
[1] Embed query ──────> Xeon 6 / OpenVINO (AMX-accelerated, <5ms)
    |
[2] Vector search ────> In-memory (would be Redis/Milvus in production)
    |
[3] Rerank candidates > Xeon 6 / OpenVINO (cross-encoder, <10ms)
    |
[4] Generate answer ──> Gaudi / vLLM (7B+ LLM, <2s)
    |
    v
Answer with citations + routing trace
```

Xeon 6 handles 3 of 4 stages. Gaudi only activates for the heavyweight generation step. The gateway returns full routing metadata showing which hardware was selected and why.

## Run

```bash
# Against a running gateway
python3 app.py --query "What is OpenShift AI?"

# Custom gateway URL
python3 app.py --gateway https://gateway.apps.cluster.example.com --query "How does AMX work?"

# JSON output for integration
python3 app.py --query "Explain model quantization" --json
```

## Partner Message

> "You don't need GPU for every AI step. Xeon 6 handles embeddings, classification,
> and reranking at wire speed. Gaudi activates only when you need it.
> Red Hat OpenShift AI orchestrates the whole thing."
