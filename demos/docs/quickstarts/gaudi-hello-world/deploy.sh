#!/usr/bin/env bash
#
# deploy.sh - Deploy Gaudi GPU inference to OpenShift/Kubernetes
#
# Usage:
#   ./deploy.sh              # Deploy with kustomize
#   ./deploy.sh --preview    # Preview manifests without applying
#   ./deploy.sh --help       # Show help
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
MANIFEST_DIR="../../../deploy/gaudi-inference"
NAMESPACE="intel-rh-gaudi-inference"

# Helper functions
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    exit 1
}

check_prerequisites() {
    info "Checking prerequisites..."

    # Check for kubectl or oc
    if command -v oc &> /dev/null; then
        KUBECTL="oc"
        info "Found oc CLI"
    elif command -v kubectl &> /dev/null; then
        KUBECTL="kubectl"
        info "Found kubectl CLI"
    else
        error "Neither 'oc' nor 'kubectl' found. Please install one of them."
    fi

    # Check for kustomize (optional if kubectl has built-in kustomize)
    if command -v kustomize &> /dev/null; then
        KUSTOMIZE="kustomize"
        info "Found kustomize CLI"
    else
        warn "kustomize not found, will use kubectl apply -k"
        KUSTOMIZE=""
    fi

    # Verify cluster connection
    if ! $KUBECTL cluster-info &> /dev/null; then
        error "Cannot connect to cluster. Please login first: $KUBECTL login ..."
    fi

    info "Connected to cluster: $($KUBECTL config current-context)"

    # Check for Gaudi GPUs (critical for this deployment)
    check_gaudi_availability
}

check_gaudi_availability() {
    info "Checking for Intel Gaudi GPU availability..."

    # Check if habana device plugin is running
    local habana_pods=$($KUBECTL get pods -n kube-system 2>/dev/null | grep habana | wc -l)

    if [ "$habana_pods" -eq 0 ]; then
        warn "Habana device plugin not found in kube-system namespace"
        warn "Gaudi GPUs may not be available"
    else
        info "Habana device plugin running ($habana_pods pod(s))"
    fi

    # Check for nodes with Gaudi resources
    local gaudi_nodes=$($KUBECTL get nodes -o json 2>/dev/null | grep -c '"habana.ai/gaudi"' || echo "0")

    if [ "$gaudi_nodes" -eq 0 ]; then
        error "No nodes with Gaudi GPU resources (habana.ai/gaudi) found!

This deployment requires Intel Gaudi GPUs. Options:
  1. Contact your cluster administrator to add Gaudi nodes
  2. Use the CPU inference path instead: cd ../cpu-hello-world

To check Gaudi availability manually:
  $KUBECTL get nodes -o json | jq '.items[].status.allocatable | select(.[\"habana.ai/gaudi\"])'"
    else
        info "Found $gaudi_nodes node(s) with Gaudi GPU resources"

        # Show available Gaudi GPUs
        local total_gaudi=$($KUBECTL get nodes -o json 2>/dev/null | \
            jq '[.items[].status.allocatable["habana.ai/gaudi"] // "0" | tonumber] | add' || echo "0")

        if [ "$total_gaudi" -gt 0 ]; then
            info "Total available Gaudi GPUs: $total_gaudi"
        fi
    fi
}

preview_manifests() {
    info "Previewing manifests..."

    cd "$MANIFEST_DIR" || error "Manifest directory not found: $MANIFEST_DIR"

    if [ -n "$KUSTOMIZE" ]; then
        $KUSTOMIZE build .
    else
        $KUBECTL kustomize .
    fi
}

deploy() {
    info "Deploying Gaudi GPU inference to cluster..."

    cd "$MANIFEST_DIR" || error "Manifest directory not found: $MANIFEST_DIR"

    # Deploy using kustomize
    if [ -n "$KUSTOMIZE" ]; then
        $KUSTOMIZE build . | $KUBECTL apply -f -
    else
        $KUBECTL apply -k .
    fi

    info "Deployment initiated successfully!"
    echo ""
    info "Monitor deployment with:"
    echo "  $KUBECTL get inferenceservice gaudi-inference-example -n $NAMESPACE -w"
    echo ""
    info "Check pods with:"
    echo "  $KUBECTL get pods -n $NAMESPACE"
    echo ""
    info "Verify Gaudi GPU assignment:"
    echo "  $KUBECTL describe pod -n $NAMESPACE <pod-name> | grep -A 5 'Limits:'"
    echo ""
    info "View logs with:"
    echo "  $KUBECTL logs -n $NAMESPACE -l serving.kserve.io/inferenceservice=gaudi-inference-example -f"
}

wait_for_ready() {
    info "Waiting for InferenceService to be ready..."

    local max_wait=300  # 5 minutes
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        if $KUBECTL get inferenceservice gaudi-inference-example -n $NAMESPACE &> /dev/null; then
            local ready=$($KUBECTL get inferenceservice gaudi-inference-example -n $NAMESPACE -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")

            if [ "$ready" == "True" ]; then
                info "InferenceService is ready!"
                return 0
            fi
        fi

        echo -n "."
        sleep 5
        elapsed=$((elapsed + 5))
    done

    echo ""
    warn "InferenceService not ready after ${max_wait}s. Check status manually."
    return 1
}

show_status() {
    info "Deployment status:"
    echo ""

    # Check namespace
    if $KUBECTL get namespace $NAMESPACE &> /dev/null; then
        echo "✓ Namespace: $NAMESPACE exists"
    else
        echo "✗ Namespace: $NAMESPACE not found"
        return 1
    fi

    # Check InferenceService
    if $KUBECTL get inferenceservice gaudi-inference-example -n $NAMESPACE &> /dev/null; then
        echo "✓ InferenceService: gaudi-inference-example exists"
        $KUBECTL get inferenceservice gaudi-inference-example -n $NAMESPACE
    else
        echo "✗ InferenceService: not found"
    fi

    echo ""

    # Check pods and Gaudi assignment
    info "Pods:"
    $KUBECTL get pods -n $NAMESPACE

    echo ""

    # Check Gaudi GPU assignment in pods
    local pods=$($KUBECTL get pods -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
    if [ -n "$pods" ]; then
        info "Gaudi GPU Assignment:"
        for pod in $pods; do
            local gaudi_limit=$($KUBECTL get pod "$pod" -n $NAMESPACE -o jsonpath='{.spec.containers[0].resources.limits.habana\.ai/gaudi}' 2>/dev/null || echo "none")
            echo "  Pod: $pod"
            echo "    habana.ai/gaudi: $gaudi_limit"
        done
    fi

    echo ""

    # Get URL
    local url=$($KUBECTL get inferenceservice gaudi-inference-example -n $NAMESPACE -o jsonpath='{.status.url}' 2>/dev/null || echo "")
    if [ -n "$url" ]; then
        info "Inference URL: $url"
    fi
}

show_help() {
    cat << EOF
Gaudi GPU Inference Deployment Script

Usage: $0 [OPTIONS]

OPTIONS:
    --preview       Preview manifests without deploying
    --wait          Deploy and wait for service to be ready
    --status        Show deployment status
    --help          Show this help message

EXAMPLES:
    # Deploy to cluster
    $0

    # Preview what will be deployed
    $0 --preview

    # Deploy and wait for ready
    $0 --wait

    # Check deployment status
    $0 --status

PREREQUISITES:
    - oc or kubectl CLI installed and configured
    - kustomize CLI (optional)
    - Access to OpenShift/Kubernetes cluster
    - Cluster logged in: oc login ... or kubectl config use-context ...
    - **Intel Gaudi GPU nodes available** (critical!)

GAUDI GPU REQUIREMENTS:
    - Habana device plugin running on Gaudi nodes
    - Nodes with habana.ai/gaudi resources
    - At least 1 Gaudi GPU available

    Check Gaudi availability:
      kubectl get nodes -o json | jq '.items[].status.allocatable | select(.[\"habana.ai/gaudi\"])'

For more information, see README.md

EOF
}

# Main execution
main() {
    local mode="deploy"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --preview)
                mode="preview"
                shift
                ;;
            --wait)
                mode="deploy-wait"
                shift
                ;;
            --status)
                mode="status"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                error "Unknown option: $1. Use --help for usage."
                ;;
        esac
    done

    # Execute based on mode
    case $mode in
        preview)
            check_prerequisites
            preview_manifests
            ;;
        deploy)
            check_prerequisites
            deploy
            ;;
        deploy-wait)
            check_prerequisites
            deploy
            wait_for_ready
            show_status
            ;;
        status)
            check_prerequisites
            show_status
            ;;
    esac
}

main "$@"
