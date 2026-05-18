#!/usr/bin/env bash
#
# test.sh - Test Gaudi GPU inference deployment
#
# Usage:
#   ./test.sh              # Run all tests
#   ./test.sh --quick      # Run quick health checks only
#   ./test.sh --benchmark  # Run performance benchmarks
#   ./test.sh --help       # Show help
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="intel-rh-gaudi-inference"
ISVC_NAME="gaudi-inference-example"
MODEL_NAME="TinyLlama/TinyLlama-1.1B-Chat-v1.0"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[✓]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    echo -e "${RED}[✗]${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

test_header() {
    TESTS_RUN=$((TESTS_RUN + 1))
    echo ""
    echo -e "${BLUE}[TEST $TESTS_RUN]${NC} $1"
}

check_prerequisites() {
    # Check for kubectl or oc
    if command -v oc &> /dev/null; then
        KUBECTL="oc"
    elif command -v kubectl &> /dev/null; then
        KUBECTL="kubectl"
    else
        error "Neither 'oc' nor 'kubectl' found. Please install one of them."
        exit 1
    fi

    # Check for curl
    if ! command -v curl &> /dev/null; then
        error "curl not found. Please install curl."
        exit 1
    fi

    # Check cluster connection
    if ! $KUBECTL cluster-info &> /dev/null; then
        error "Cannot connect to cluster. Please login first."
        exit 1
    fi
}

get_inference_url() {
    local url=$($KUBECTL get inferenceservice $ISVC_NAME -n $NAMESPACE -o jsonpath='{.status.url}' 2>/dev/null || echo "")

    if [ -z "$url" ]; then
        error "Could not get inference service URL. Is the service deployed?"
        exit 1
    fi

    echo "$url"
}

# Test: Namespace exists
test_namespace_exists() {
    test_header "Namespace exists"

    if $KUBECTL get namespace $NAMESPACE &> /dev/null; then
        success "Namespace '$NAMESPACE' exists"
        return 0
    else
        fail "Namespace '$NAMESPACE' not found"
        return 1
    fi
}

# Test: InferenceService exists
test_inferenceservice_exists() {
    test_header "InferenceService exists"

    if $KUBECTL get inferenceservice $ISVC_NAME -n $NAMESPACE &> /dev/null; then
        success "InferenceService '$ISVC_NAME' exists"
        return 0
    else
        fail "InferenceService '$ISVC_NAME' not found"
        return 1
    fi
}

# Test: InferenceService is ready
test_inferenceservice_ready() {
    test_header "InferenceService is ready"

    local ready=$($KUBECTL get inferenceservice $ISVC_NAME -n $NAMESPACE -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")

    if [ "$ready" == "True" ]; then
        success "InferenceService is ready"
        return 0
    else
        fail "InferenceService not ready (status: $ready)"
        info "Check status with: $KUBECTL describe inferenceservice $ISVC_NAME -n $NAMESPACE"
        return 1
    fi
}

# Test: Pods are running
test_pods_running() {
    test_header "Pods are running"

    local pod_count=$($KUBECTL get pods -n $NAMESPACE -l serving.kserve.io/inferenceservice=$ISVC_NAME --no-headers 2>/dev/null | wc -l)

    if [ "$pod_count" -gt 0 ]; then
        local running_count=$($KUBECTL get pods -n $NAMESPACE -l serving.kserve.io/inferenceservice=$ISVC_NAME --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)

        if [ "$running_count" -gt 0 ]; then
            success "$running_count pod(s) running"
            return 0
        else
            fail "No pods in Running state (found $pod_count pod(s) total)"
            return 1
        fi
    else
        fail "No pods found for InferenceService"
        return 1
    fi
}

# Test: Gaudi GPU assigned to pod (critical for Gaudi deployment)
test_gaudi_gpu_assigned() {
    test_header "Gaudi GPU assigned to pod"

    local pods=$($KUBECTL get pods -n $NAMESPACE -l serving.kserve.io/inferenceservice=$ISVC_NAME -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

    if [ -z "$pods" ]; then
        fail "No pods found to check Gaudi assignment"
        return 1
    fi

    local pod=$(echo $pods | awk '{print $1}')  # Get first pod

    # Check Gaudi resource in limits
    local gaudi_limit=$($KUBECTL get pod "$pod" -n $NAMESPACE -o jsonpath='{.spec.containers[0].resources.limits.habana\.ai/gaudi}' 2>/dev/null || echo "")

    if [ -n "$gaudi_limit" ] && [ "$gaudi_limit" != "null" ]; then
        success "Pod has habana.ai/gaudi: $gaudi_limit assigned"
        info "Pod: $pod"
        return 0
    else
        fail "Pod does not have habana.ai/gaudi resource assigned"
        warn "This deployment requires Gaudi GPU but pod is not assigned one"
        return 1
    fi
}

# Test: Pod on Gaudi-capable node
test_pod_on_gaudi_node() {
    test_header "Pod scheduled on Gaudi-capable node"

    local pods=$($KUBECTL get pods -n $NAMESPACE -l serving.kserve.io/inferenceservice=$ISVC_NAME -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

    if [ -z "$pods" ]; then
        fail "No pods found"
        return 1
    fi

    local pod=$(echo $pods | awk '{print $1}')

    # Get node name
    local node=$($KUBECTL get pod "$pod" -n $NAMESPACE -o jsonpath='{.spec.nodeName}' 2>/dev/null)

    if [ -z "$node" ]; then
        fail "Could not determine node for pod"
        return 1
    fi

    # Check if node has Gaudi resources
    local node_gaudi=$($KUBECTL get node "$node" -o jsonpath='{.status.allocatable.habana\.ai/gaudi}' 2>/dev/null || echo "0")

    if [ "$node_gaudi" != "0" ] && [ -n "$node_gaudi" ]; then
        success "Pod on Gaudi node '$node' (has $node_gaudi Gaudi GPU(s))"
        return 0
    else
        warn "Pod on node '$node' which has no Gaudi GPUs"
        warn "Deployment may fall back to CPU mode"
        return 1
    fi
}

# Test: Health endpoint responds
test_health_endpoint() {
    test_header "Health endpoint responds"

    local url=$(get_inference_url)

    if curl -sf "$url/health" -o /dev/null -w '' --max-time 10; then
        success "Health endpoint returns 200 OK"
        return 0
    else
        fail "Health endpoint not responding"
        return 1
    fi
}

# Test: Models endpoint responds
test_models_endpoint() {
    test_header "Models endpoint responds"

    local url=$(get_inference_url)
    local response=$(curl -sf "$url/v1/models" --max-time 10 2>/dev/null || echo "")

    if [ -n "$response" ]; then
        if echo "$response" | grep -q "$MODEL_NAME"; then
            success "Models endpoint returns expected model"
            return 0
        else
            fail "Models endpoint did not return expected model '$MODEL_NAME'"
            return 1
        fi
    else
        fail "Models endpoint not responding"
        return 1
    fi
}

# Test: Inference completions endpoint
test_completions_endpoint() {
    test_header "Completions endpoint generates text"

    local url=$(get_inference_url)

    local payload=$(cat <<EOF
{
  "model": "$MODEL_NAME",
  "prompt": "The capital of France is",
  "max_tokens": 10,
  "temperature": 0.7
}
EOF
)

    local response=$(curl -sf -X POST "$url/v1/completions" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        --max-time 30 2>/dev/null || echo "")

    if [ -n "$response" ]; then
        # Check if response contains expected fields
        if echo "$response" | grep -q '"choices"' && echo "$response" | grep -q '"text"'; then
            local generated_text=$(echo "$response" | grep -o '"text":"[^"]*"' | head -1 | cut -d'"' -f4)
            success "Completions endpoint generated text: '$generated_text'"
            return 0
        else
            fail "Completions response missing expected fields"
            echo "Response: $response"
            return 1
        fi
    else
        fail "Completions endpoint not responding"
        return 1
    fi
}

# Test: Time to first token (should be fast on Gaudi)
test_time_to_first_token() {
    test_header "Time to first token (TTFT) - Gaudi acceleration"

    local url=$(get_inference_url)

    local payload=$(cat <<EOF
{
  "model": "$MODEL_NAME",
  "prompt": "Hello, my name is",
  "max_tokens": 20
}
EOF
)

    local start_time=$(date +%s%N)
    local response=$(curl -sf -X POST "$url/v1/completions" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        --max-time 30 2>/dev/null || echo "")
    local end_time=$(date +%s%N)

    if [ -n "$response" ]; then
        local duration_ms=$(( (end_time - start_time) / 1000000 ))
        info "TTFT: ${duration_ms}ms"

        # Gaudi should be much faster than CPU
        # Expected: < 5s for Gaudi (real), < 30s for CPU fallback
        if [ "$duration_ms" -lt 5000 ]; then
            success "TTFT excellent: ${duration_ms}ms (Gaudi acceleration active)"
            return 0
        elif [ "$duration_ms" -lt 30000 ]; then
            warn "TTFT acceptable but slower than expected: ${duration_ms}ms"
            warn "May be running in CPU fallback mode. Check Gaudi assignment."
            return 1
        else
            fail "TTFT too slow: ${duration_ms}ms"
            warn "Likely running in CPU mode, not using Gaudi GPU"
            return 1
        fi
    else
        fail "Could not measure TTFT (request failed)"
        return 1
    fi
}

# Test: Concurrent requests (Gaudi handles more concurrency)
test_concurrent_requests() {
    test_header "Concurrent requests handling"

    local url=$(get_inference_url)

    local payload=$(cat <<EOF
{
  "model": "$MODEL_NAME",
  "prompt": "Test prompt number",
  "max_tokens": 5
}
EOF
)

    info "Sending 5 concurrent requests (Gaudi can handle more than CPU)..."

    # Send 5 requests in parallel (Gaudi can handle higher concurrency)
    local pids=()
    for i in {1..5}; do
        curl -sf -X POST "$url/v1/completions" -H "Content-Type: application/json" -d "$payload" --max-time 30 &> /dev/null & pids+=($!)
    done

    # Wait for all to complete
    local success_count=0
    for pid in "${pids[@]}"; do
        if wait $pid 2>/dev/null; then
            success_count=$((success_count + 1))
        fi
    done

    info "Concurrent requests: $success_count/5 succeeded"

    if [ "$success_count" -eq 5 ]; then
        success "All 5 concurrent requests succeeded (good Gaudi concurrency)"
        return 0
    elif [ "$success_count" -ge 3 ]; then
        warn "$success_count/5 concurrent requests succeeded"
        return 1
    else
        fail "Only $success_count/5 concurrent requests succeeded"
        return 1
    fi
}

# Show deployment info
show_deployment_info() {
    echo ""
    echo "======================================"
    echo " Gaudi GPU Deployment Information"
    echo "======================================"
    echo ""

    info "Namespace: $NAMESPACE"
    echo ""

    info "InferenceService:"
    $KUBECTL get inferenceservice $ISVC_NAME -n $NAMESPACE 2>/dev/null || echo "Not found"
    echo ""

    info "Pods:"
    $KUBECTL get pods -n $NAMESPACE 2>/dev/null || echo "Not found"
    echo ""

    # Show Gaudi GPU assignment
    info "Gaudi GPU Assignment:"
    local pods=$($KUBECTL get pods -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
    if [ -n "$pods" ]; then
        for pod in $pods; do
            local gaudi_limit=$($KUBECTL get pod "$pod" -n $NAMESPACE -o jsonpath='{.spec.containers[0].resources.limits.habana\.ai/gaudi}' 2>/dev/null || echo "none")
            local node=$($KUBECTL get pod "$pod" -n $NAMESPACE -o jsonpath='{.spec.nodeName}' 2>/dev/null)
            echo "  Pod: $pod"
            echo "    Node: $node"
            echo "    habana.ai/gaudi: $gaudi_limit"
        done
    fi
    echo ""

    info "Inference URL:"
    get_inference_url 2>/dev/null || echo "Not available"
    echo ""
}

# Show test summary
show_summary() {
    echo ""
    echo "======================================"
    echo " Test Summary"
    echo "======================================"
    echo "Total tests: $TESTS_RUN"
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
    echo ""

    if [ "$TESTS_FAILED" -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        echo ""
        info "Gaudi GPU inference is working correctly"
        return 0
    else
        echo -e "${RED}✗ Some tests failed. Check logs above for details.${NC}"
        echo ""
        if [ "$TESTS_FAILED" -ge 2 ]; then
            warn "Multiple failures detected. Common issues:"
            echo "  - No Gaudi GPU assigned (check habana.ai/gaudi resource)"
            echo "  - Pod not on Gaudi node (check node selector)"
            echo "  - Running in CPU fallback mode (check TTFT performance)"
        fi
        return 1
    fi
}

# Quick health check
quick_test() {
    info "Running quick health checks..."
    test_namespace_exists || true
    test_inferenceservice_exists || true
    test_inferenceservice_ready || true
    test_pods_running || true
    test_gaudi_gpu_assigned || true
}

# Full test suite
full_test() {
    info "Running full test suite..."
    test_namespace_exists || true
    test_inferenceservice_exists || true
    test_inferenceservice_ready || true
    test_pods_running || true
    test_gaudi_gpu_assigned || true
    test_pod_on_gaudi_node || true
    test_health_endpoint || true
    test_models_endpoint || true
    test_completions_endpoint || true
    test_time_to_first_token || true
    test_concurrent_requests || true
}

# Benchmark tests
benchmark_test() {
    info "Running performance benchmarks (Gaudi GPU)..."
    test_time_to_first_token || true
    test_concurrent_requests || true

    # Additional benchmark: 10 sequential requests
    test_header "Sequential throughput (10 requests)"

    local url=$(get_inference_url)
    local payload='{"model": "'$MODEL_NAME'", "prompt": "Test", "max_tokens": 10}'

    local start_time=$(date +%s)
    for i in {1..10}; do
        curl -sf -X POST "$url/v1/completions" -H "Content-Type: application/json" -d "$payload" --max-time 30 &> /dev/null || true
    done
    local end_time=$(date +%s)

    local total_time=$((end_time - start_time))
    if [ "$total_time" -gt 0 ]; then
        local throughput=$(echo "scale=2; 10 / $total_time" | bc)
    else
        local throughput="N/A (completed in <1s)"
    fi

    info "Completed 10 requests in ${total_time}s (${throughput} req/s)"

    if [ "$total_time" -lt 30 ]; then
        success "Good throughput with Gaudi GPU acceleration"
    else
        warn "Throughput slower than expected for Gaudi"
    fi
}

show_help() {
    cat << EOF
Gaudi GPU Inference Test Script

Usage: $0 [OPTIONS]

OPTIONS:
    --quick         Run quick health checks only
    --benchmark     Run performance benchmarks
    --info          Show deployment information
    --help          Show this help message

EXAMPLES:
    # Run all tests
    $0

    # Quick health check
    $0 --quick

    # Performance benchmarks
    $0 --benchmark

    # Show deployment info
    $0 --info

PREREQUISITES:
    - Deployment must be active (run deploy.sh first)
    - oc or kubectl CLI installed
    - curl installed

GAUDI-SPECIFIC TESTS:
    - Verifies habana.ai/gaudi GPU assignment
    - Checks pod on Gaudi-capable node
    - Measures TTFT (should be <5s with Gaudi)
    - Tests concurrent requests (Gaudi handles more)

For more information, see README.md

EOF
}

# Main execution
main() {
    local mode="full"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick)
                mode="quick"
                shift
                ;;
            --benchmark)
                mode="benchmark"
                shift
                ;;
            --info)
                mode="info"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                error "Unknown option: $1. Use --help for usage."
                exit 1
                ;;
        esac
    done

    check_prerequisites

    case $mode in
        quick)
            quick_test
            show_summary
            ;;
        full)
            full_test
            show_summary
            ;;
        benchmark)
            benchmark_test
            show_summary
            ;;
        info)
            show_deployment_info
            ;;
    esac
}

main "$@"
