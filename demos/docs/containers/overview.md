# Container Testing for OpenShift AI

Container builds and testing for Intel partnership AI workloads.

## Ollama Test Container

**Purpose**: Test CPU-based LLM inference locally before deploying to Xeon6 nodes.

**Quick Test**:
```bash
./test-llm-cpu.sh
```

**Manual Usage**:
```bash
# Start Ollama
podman run -d --name ollama-test -p 11434:11434 docker.io/ollama/ollama:latest

# Pull a model
podman exec ollama-test ollama pull tinyllama

# Run inference
podman exec ollama-test ollama run tinyllama "Your prompt here"

# Stop container
podman stop ollama-test

# Remove container
podman rm ollama-test
```

## Available Models
- `tinyllama` - 1.1B params, good for quick testing
- `phi3` - 3.8B params, better quality
- `llama2` - 7B params, production testing

## Next Steps
1. Test containerized models locally
2. Create Containerfiles for custom AI apps
3. Build and push to Red Hat registries
4. Deploy to OpenShift AI cluster
