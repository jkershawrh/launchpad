#!/bin/bash
# Test CPU-based LLM inference with Ollama
# Relevant for Intel Xeon6 CPU inference testing
set -euo pipefail

echo "Testing CPU-based LLM inference..."
echo "=================================="
echo ""

# Check if Ollama container is running
if ! podman ps | grep -q ollama-test; then
    echo "Starting Ollama container..."
    podman start ollama-test || podman run -d --name ollama-test -p 11434:11434 docker.io/ollama/ollama:latest
    sleep 3
fi

# List available models
echo "Available models:"
podman exec ollama-test ollama list

echo ""
echo "Running inference test..."
echo ""

# Test inference
podman exec ollama-test ollama run tinyllama "Explain Intel Xeon6 for LLM inference in one sentence."

echo ""
echo "Test complete!"
