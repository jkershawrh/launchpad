#!/usr/bin/env bash
#
# discover-cluster.sh - Discover OpenShift cluster configuration
#
# This script discovers cluster information to fill [TBD] placeholders
# in deployment manifests and documentation.
#
# Usage:
#   ./discover-cluster.sh                    # Output to stdout
#   ./discover-cluster.sh --output FILE      # Output to file
#   ./discover-cluster.sh --dry-run          # Generate sample output without cluster
#   ./discover-cluster.sh --help             # Show help
#

set -euo pipefail

# Configuration
OUTPUT_FILE=""
DRY_RUN=false
VERBOSE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
info() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${GREEN}[INFO]${NC} $1" >&2
    fi
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

show_help() {
    cat << EOF
OpenShift Cluster Discovery Tool

Discovers cluster configuration including:
  - Cluster version and API URL
  - Node types (CPU, Gaudi GPU)
  - Node labels for scheduling
  - Installed operators
  - Image registry information

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -o, --output FILE    Write output to FILE instead of stdout
    -d, --dry-run        Generate sample output without connecting to cluster
    -v, --verbose        Verbose output
    -h, --help           Show this help message

EXAMPLES:
    # Discover cluster and output to stdout
    $0

    # Save to file
    $0 --output cluster-info.yaml

    # Generate sample output for testing
    $0 --dry-run

PREREQUISITES:
    - oc or kubectl CLI installed
    - Logged into OpenShift cluster (unless --dry-run)

OUTPUT FORMAT:
    YAML format with sections:
      - cluster: version, API URL
      - nodes: total count, CPU nodes, Gaudi nodes with labels
      - operators: installed operators
      - registry: image registry information

EOF
}

check_prerequisites() {
    # Skip checks if dry-run mode
    if [ "$DRY_RUN" = true ]; then
        info "Dry-run mode: skipping prerequisite checks"
        return 0
    fi

    # Check for oc or kubectl
    if command -v oc &> /dev/null; then
        KUBECTL="oc"
    elif command -v kubectl &> /dev/null; then
        KUBECTL="kubectl"
    else
        error "Neither 'oc' nor 'kubectl' found. Please install one of them."
        return 1
    fi

    info "Using CLI: $KUBECTL"

    # Check cluster connection
    if ! $KUBECTL cluster-info &> /dev/null; then
        error "Cannot connect to cluster. Please login first or use --dry-run."
        return 1
    fi
    info "Connected to cluster"

    return 0
}

discover_cluster_info() {
    info "Discovering cluster information..."

    if [ "$DRY_RUN" = true ]; then
        # Sample data for dry-run
        CLUSTER_VERSION="4.15.0"
        CLUSTER_API_URL="https://api.example.openshift.com:6443"
    else
        # Real cluster discovery
        CLUSTER_VERSION=$($KUBECTL version -o json 2>/dev/null | grep -o '"gitVersion": "[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
        CLUSTER_API_URL=$($KUBECTL cluster-info | grep 'Kubernetes control plane' | awk '{print $NF}' || echo "unknown")
    fi

    info "Cluster version: $CLUSTER_VERSION"
}

discover_nodes() {
    info "Discovering nodes..."

    if [ "$DRY_RUN" = true ]; then
        # Sample data for dry-run
        TOTAL_NODES=6
        GAUDI_NODE_COUNT=2
        CPU_NODE_COUNT=4
        GAUDI_NODES='[{"name":"gaudi-worker-1","labels":{"node-role.kubernetes.io/worker":"","accelerator":"gaudi","intel.feature.node.kubernetes.io/gaudi":"true"}},{"name":"gaudi-worker-2","labels":{"node-role.kubernetes.io/worker":"","accelerator":"gaudi","intel.feature.node.kubernetes.io/gaudi":"true"}}]'
        CPU_NODES='[{"name":"cpu-worker-1","labels":{"node-role.kubernetes.io/worker":"","cpu":"xeon6"}},{"name":"cpu-worker-2","labels":{"node-role.kubernetes.io/worker":"","cpu":"xeon6"}},{"name":"cpu-worker-3","labels":{"node-role.kubernetes.io/worker":"","cpu":"xeon6"}},{"name":"cpu-worker-4","labels":{"node-role.kubernetes.io/worker":"","cpu":"xeon6"}}]'
    else
        # Real node discovery
        TOTAL_NODES=$($KUBECTL get nodes --no-headers 2>/dev/null | wc -l || echo "0")

        # Discover Gaudi nodes (nodes with habana.ai/gaudi resource)
        GAUDI_NODE_COUNT=$($KUBECTL get nodes -o json 2>/dev/null | \
            jq '[.items[] | select(.status.allocatable["habana.ai/gaudi"] != null)] | length' || echo "0")

        # Get Gaudi node details
        GAUDI_NODES=$($KUBECTL get nodes -o json 2>/dev/null | \
            jq -c '[.items[] | select(.status.allocatable["habana.ai/gaudi"] != null) | {name: .metadata.name, labels: .metadata.labels}]' || echo "[]")

        # CPU-only nodes (all non-Gaudi worker nodes)
        CPU_NODE_COUNT=$($KUBECTL get nodes -l node-role.kubernetes.io/worker -o json 2>/dev/null | \
            jq '[.items[] | select(.status.allocatable["habana.ai/gaudi"] == null)] | length' || echo "0")

        # Get CPU node details
        CPU_NODES=$($KUBECTL get nodes -l node-role.kubernetes.io/worker -o json 2>/dev/null | \
            jq -c '[.items[] | select(.status.allocatable["habana.ai/gaudi"] == null) | {name: .metadata.name, labels: .metadata.labels}]' || echo "[]")
    fi

    info "Total nodes: $TOTAL_NODES"
    info "Gaudi GPU nodes: $GAUDI_NODE_COUNT"
    info "CPU nodes: $CPU_NODE_COUNT"
}

discover_operators() {
    info "Discovering operators..."

    if [ "$DRY_RUN" = true ]; then
        # Sample data for dry-run
        HAS_OPENSHIFT_AI="true"
        HAS_KSERVE="true"
        HAS_HABANA_PLUGIN="true"
        OPERATORS='{"rhods":{"installed":true,"version":"2.8.0"},"kserve":{"installed":true,"version":"0.11.0"},"habana_device_plugin":{"installed":true,"version":"1.14.0"}}'
    else
        # Real operator discovery
        # Check for Red Hat OpenShift AI (RHODS/RHOAI)
        if $KUBECTL get csv -A 2>/dev/null | grep -q "rhods-operator\|rhoai-operator"; then
            HAS_OPENSHIFT_AI="true"
        else
            HAS_OPENSHIFT_AI="false"
        fi

        # Check for KServe
        if $KUBECTL get namespace knative-serving &>/dev/null || \
           $KUBECTL get pods -n redhat-ods-applications 2>/dev/null | grep -q kserve; then
            HAS_KSERVE="true"
        else
            HAS_KSERVE="false"
        fi

        # Check for Habana device plugin (DaemonSet in kube-system or habana-system)
        if $KUBECTL get ds -A 2>/dev/null | grep -q "habana-device-plugin\|intel-gaudi-device-plugin"; then
            HAS_HABANA_PLUGIN="true"
        else
            HAS_HABANA_PLUGIN="false"
        fi

        OPERATORS="{\"rhods\":{\"installed\":$HAS_OPENSHIFT_AI},\"kserve\":{\"installed\":$HAS_KSERVE},\"habana_device_plugin\":{\"installed\":$HAS_HABANA_PLUGIN}}"
    fi

    info "OpenShift AI: $HAS_OPENSHIFT_AI"
    info "KServe: $HAS_KSERVE"
    info "Habana Device Plugin: $HAS_HABANA_PLUGIN"
}

discover_registry() {
    info "Discovering image registry..."

    if [ "$DRY_RUN" = true ]; then
        # Sample data for dry-run
        INTERNAL_REGISTRY="image-registry.openshift-image-registry.svc:5000"
        REGISTRY_ROUTE="default-route-openshift-image-registry.apps.example.openshift.com"
    else
        # Real registry discovery
        INTERNAL_REGISTRY=$($KUBECTL get svc -n openshift-image-registry image-registry -o jsonpath='{.metadata.name}:{.spec.ports[0].port}' 2>/dev/null || echo "")

        if [ -n "$INTERNAL_REGISTRY" ]; then
            INTERNAL_REGISTRY="image-registry.openshift-image-registry.svc:5000"
        fi

        REGISTRY_ROUTE=$($KUBECTL get route -n openshift-image-registry default-route -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
    fi

    if [ -n "$INTERNAL_REGISTRY" ]; then
        info "Internal registry: $INTERNAL_REGISTRY"
    else
        info "Internal registry: not found"
    fi
}

generate_output() {
    info "Generating output..."

    # Generate YAML output
    cat << EOF
# OpenShift Cluster Discovery
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Tool: discover-cluster.sh

cluster:
  version: "$CLUSTER_VERSION"
  api_url: "$CLUSTER_API_URL"

nodes:
  total: $TOTAL_NODES
  cpu_count: $CPU_NODE_COUNT
  gaudi_count: $GAUDI_NODE_COUNT
  cpu_nodes: $CPU_NODES
  gaudi_nodes: $GAUDI_NODES

operators:
  openshift_ai:
    installed: $HAS_OPENSHIFT_AI
  kserve:
    installed: $HAS_KSERVE
  habana_device_plugin:
    installed: $HAS_HABANA_PLUGIN

registry:
  internal: "$INTERNAL_REGISTRY"
  external_route: "$REGISTRY_ROUTE"

# Recommended manifest values:
recommendations:
  cpu_inference:
    node_selector:
      node-role.kubernetes.io/worker: ""
    # Update based on actual node labels discovered above
  gaudi_inference:
    node_selector:
      node-role.kubernetes.io/worker: ""
      # Add specific Gaudi node label if available
    resources:
      limits:
        habana.ai/gaudi: "1"
EOF
}

# Main execution
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -o|--output)
                OUTPUT_FILE="$2"
                shift 2
                ;;
            -d|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                error "Unknown option: $1. Use --help for usage."
                exit 1
                ;;
        esac
    done

    # Check prerequisites
    if ! check_prerequisites; then
        exit 1
    fi

    # Discover cluster information
    discover_cluster_info
    discover_nodes
    discover_operators
    discover_registry

    # Generate output
    if [ -n "$OUTPUT_FILE" ]; then
        generate_output > "$OUTPUT_FILE"
        info "Output written to: $OUTPUT_FILE"
    else
        generate_output
    fi
}

main "$@"
