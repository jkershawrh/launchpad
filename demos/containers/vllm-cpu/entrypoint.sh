#!/bin/bash
# Entrypoint script for vLLM CPU container

set -e

# Function to handle shutdown gracefully
cleanup() {
    echo "Received shutdown signal, cleaning up..."
    if [ -n "$SERVER_PID" ]; then
        kill -TERM "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    exit 0
}

# Trap SIGTERM and SIGINT for graceful shutdown
trap cleanup SIGTERM SIGINT

# If first argument is --help, show help
if [ "$1" = "--help" ]; then
    echo "vLLM CPU Inference Container"
    echo ""
    echo "Usage:"
    echo "  Run inference server:"
    echo "    podman run -p 8000:8000 -e MODEL_NAME=<model> vllm-cpu:latest"
    echo ""
    echo "  Interactive Python:"
    echo "    podman run -it vllm-cpu:latest python3"
    echo ""
    echo "Environment variables:"
    echo "  MODEL_NAME  - HuggingFace model to load (default: TinyLlama/TinyLlama-1.1B-Chat-v1.0)"
    echo "  HF_TOKEN    - HuggingFace API token for private models"
    echo "  PORT        - Server port (default: 8000)"
    exit 0
fi

# If arguments provided, execute them
if [ $# -gt 0 ]; then
    exec "$@"
fi

# Default: run inference server
echo "Starting CPU Inference Server..."
echo "Model: ${MODEL_NAME:-TinyLlama/TinyLlama-1.1B-Chat-v1.0}"
echo "Port: ${PORT:-8000}"

exec python3 /opt/app-root/src/inference_server.py
