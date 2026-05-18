#!/bin/bash
# Local test script for vLLM CPU container
# Tests inference with a small model

set -e

CONTAINER_NAME="vllm-cpu-local-test"
IMAGE_NAME="localhost/vllm-cpu:test"
MODEL="TinyLlama/TinyLlama-1.1B-Chat-v1.0"
PORT=8000

echo "========================================"
echo "vLLM CPU Local Inference Test"
echo "========================================"
echo ""

# Cleanup function
cleanup() {
    echo "Cleaning up..."
    podman rm -f "$CONTAINER_NAME" 2>/dev/null || true
}

# Trap exit to ensure cleanup
trap cleanup EXIT

# Check if image exists
echo "Checking if container image exists..."
if ! podman images -q "$IMAGE_NAME" | grep -q .; then
    echo "ERROR: Container image $IMAGE_NAME not found."
    echo "Build it first with: podman build -t $IMAGE_NAME containers/vllm-cpu/"
    exit 1
fi
echo "✓ Image found"
echo ""

# Start container
echo "Starting vLLM server container..."
podman run -d \
    --name "$CONTAINER_NAME" \
    -p ${PORT}:8000 \
    "$IMAGE_NAME" \
    vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 1024 \
    --dtype float16

echo "Container started. Waiting for vLLM to initialize..."
echo ""

# Wait for health endpoint (max 120 seconds)
echo "Waiting for health endpoint..."
for i in {1..24}; do
    if curl -f -s http://localhost:${PORT}/health > /dev/null 2>&1; then
        echo "✓ Health endpoint responding"
        break
    fi

    if [ $i -eq 24 ]; then
        echo "ERROR: Health endpoint not responding after 120 seconds"
        echo ""
        echo "Container logs:"
        podman logs "$CONTAINER_NAME"
        exit 1
    fi

    echo "  Attempt $i/24... waiting 5s"
    sleep 5
done
echo ""

# Test inference
echo "Testing inference..."
RESPONSE=$(curl -s http://localhost:${PORT}/v1/completions \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"$MODEL\",
        \"prompt\": \"Why is CPU-based inference important for LLMs?\",
        \"max_tokens\": 50,
        \"temperature\": 0.7
    }")

echo "Response received:"
echo "$RESPONSE" | python3 -m json.tool || echo "$RESPONSE"
echo ""

# Check if response contains expected fields
if echo "$RESPONSE" | grep -q '"choices"'; then
    echo "✓ Inference successful - response contains completion"
else
    echo "✗ Inference failed - unexpected response format"
    exit 1
fi

# Extract generated text
GENERATED_TEXT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['choices'][0]['text'])" 2>/dev/null || echo "")

if [ -n "$GENERATED_TEXT" ]; then
    echo "✓ Generated text:"
    echo "  \"$GENERATED_TEXT\""
else
    echo "⚠ Could not extract generated text (might be empty)"
fi
echo ""

# Test metrics endpoint
echo "Checking metrics endpoint..."
METRICS=$(curl -s http://localhost:${PORT}/metrics 2>/dev/null || echo "")
if [ -n "$METRICS" ]; then
    echo "✓ Metrics endpoint responding"
else
    echo "⚠ Metrics endpoint not available (this is OK for basic testing)"
fi
echo ""

echo "========================================"
echo "✓ All tests passed!"
echo "========================================"
echo ""
echo "Container is still running. To interact:"
echo "  curl http://localhost:${PORT}/v1/completions -H 'Content-Type: application/json' -d '{...}'"
echo ""
echo "To stop:"
echo "  podman stop $CONTAINER_NAME"
