# vLLM CPU Inference Container

Container optimized for CPU-based LLM inference on Intel Xeon6 processors.

## Build

```bash
podman build -t vllm-cpu:latest .
```

## Run Locally

### Test with TinyLlama (smallest model for quick testing):

```bash
# Run vLLM server with model
podman run -d \
  --name vllm-cpu \
  -p 8000:8000 \
  vllm-cpu:latest \
  vllm.entrypoints.openai.api_server \
  --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 2048
```

### Test inference:

```bash
curl http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "prompt": "Why is CPU-based LLM inference important?",
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Check health:

```bash
curl http://localhost:8000/health
```

## Deploy to OpenShift

See `../../deploy/cpu-inference/` for deployment manifests.

## Environment Variables

- `HF_TOKEN` - HuggingFace API token (for private models)
- `MODEL_PATH` - Path to local model files (if not using HF)
- `VLLM_LOGGING_LEVEL` - Log level (INFO, DEBUG, WARNING)

## Container Specifications

- **Base Image**: registry.access.redhat.com/ubi9/python-311
- **User**: Non-root (UID 1001)
- **Port**: 8000 (vLLM API)
- **Health Check**: `/health` endpoint
- **Size**: ~3-4GB (depending on dependencies)

## Testing

Run automated tests:

```bash
cd ../..
make test-stage-1
```

## Security

- Runs as non-root user
- No privileged capabilities required
- Red Hat UBI base for CVE patching support
- Regular security scans with Trivy

## Performance

Optimized for Intel Xeon6:
- CPU-only inference
- Suitable for smaller models (< 3B parameters)
- Best for batch processing or latency-tolerant workloads
- Recommended: 4-8 CPU cores, 8-16GB RAM per instance

## Supported Models

Test models (all Apache 2.0 or MIT licensed):
- TinyLlama/TinyLlama-1.1B-Chat-v1.0 (1.1B)
- microsoft/phi-2 (2.7B)
- microsoft/Phi-3-mini-4k-instruct (3.8B)

**Note**: Model selection should be approved through Intel-RH model governance process before partner demos.
