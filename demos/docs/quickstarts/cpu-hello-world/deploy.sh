#!/usr/bin/env bash
#
# deploy.sh - Deploy CPU inference to OpenShift/Kubernetes
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
MANIFEST_DIR="../../../deploy/cpu-inference"
NAMESPACE="intel-rh-cpu-inference"

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
    info "Deploying CPU inference to cluster..."

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
    echo "  $KUBECTL get inferenceservice cpu-inference-example -n $NAMESPACE -w"
    echo ""
    info "Check pods with:"
    echo "  $KUBECTL get pods -n $NAMESPACE"
    echo ""
    info "View logs with:"
    echo "  $KUBECTL logs -n $NAMESPACE -l serving.kserve.io/inferenceservice=cpu-inference-example -f"
}

wait_for_ready() {
    info "Waiting for InferenceService to be ready..."

    local max_wait=300  # 5 minutes
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        if $KUBECTL get inferenceservice cpu-inference-example -n $NAMESPACE &> /dev/null; then
            local ready=$($KUBECTL get inferenceservice cpu-inference-example -n $NAMESPACE -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")

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
    if $KUBECTL get inferenceservice cpu-inference-example -n $NAMESPACE &> /dev/null; then
        echo "✓ InferenceService: cpu-inference-example exists"
        $KUBECTL get inferenceservice cpu-inference-example -n $NAMESPACE
    else
        echo "✗ InferenceService: not found"
    fi

    echo ""

    # Check pods
    info "Pods:"
    $KUBECTL get pods -n $NAMESPACE

    echo ""

    # Get URL
    local url=$($KUBECTL get inferenceservice cpu-inference-example -n $NAMESPACE -o jsonpath='{.status.url}' 2>/dev/null || echo "")
    if [ -n "$url" ]; then
        info "Inference URL: $url"
    fi
}

show_help() {
    cat << EOF
CPU Inference Deployment Script

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
