#!/bin/bash
#
# Entrypoint for vLLM Gaudi Inference Container
#
# V1: Mock mode for local testing
# V2: Real Gaudi mode when deployed to cluster

set -e

# If arguments provided, run them directly without banner
# (This allows commands like "id -u" to work cleanly for tests)
if [ $# -gt 0 ]; then
    exec "$@"
fi

# No arguments: starting inference server
# Trap SIGTERM for graceful shutdown
shutdown() {
    echo "Received SIGTERM, shutting down gracefully..."
    if [ -n "$SERVER_PID" ]; then
        kill -TERM "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    exit 0
}

trap shutdown SIGTERM SIGINT

# Configuration
MODEL_NAME="${MODEL_NAME:-TinyLlama/TinyLlama-1.1B-Chat-v1.0}"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo "========================================"
echo " vLLM Gaudi Inference Server V1"
echo "========================================"
echo "Model: $MODEL_NAME"
echo "Port: $PORT"
echo "Host: $HOST"
echo "Mock Mode: ${HABANA_USE_MOCK:-true}"
echo "========================================"

# Check for Gaudi accelerator devices
echo "Checking for Gaudi accelerator devices..."
if [ -e /dev/accel/accel0 ]; then
    ACCEL_COUNT=$(ls -1 /dev/accel/accel* 2>/dev/null | wc -l)
    echo "Found $ACCEL_COUNT Gaudi accelerator device(s)"
elif command -v hl-smi &>/dev/null; then
    echo "Checking via hl-smi..."
    hl-smi 2>/dev/null || echo "WARNING: hl-smi returned non-zero"
else
    echo "WARNING: No Gaudi accelerator devices found at /dev/accel/"
    echo "Falling back to CPU mode"
fi

# Display Habana environment
echo "Habana environment:"
echo "  HABANA_VISIBLE_DEVICES=${HABANA_VISIBLE_DEVICES:-not set}"

echo "Starting inference server..."
python3 /opt/app-root/src/inference_server.py &
SERVER_PID=$!

# Wait for server to exit
wait "$SERVER_PID"
