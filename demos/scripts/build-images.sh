#!/usr/bin/env bash
#
# build-images.sh - Build and push Intel-RH AI Platform container images
#
# Usage:
#   ./build-images.sh --target cpu                         # Build CPU image locally
#   ./build-images.sh --target gaudi                       # Build Gaudi image locally
#   ./build-images.sh --target all                         # Build both images
#   ./build-images.sh --target cpu --push --registry quay.io/org  # Build and push
#   ./build-images.sh --target cpu --dry-run               # Show commands only
#   ./build-images.sh --help                               # Show help
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
TARGET=""
REGISTRY="localhost"
TAG="latest"
PUSH=false
DRY_RUN=false
CONTAINER_TOOL=""

# Image names
CPU_IMAGE="vllm-cpu"
GAUDI_IMAGE="vllm-gaudi"

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CPU_DIR="$PROJECT_ROOT/containers/vllm-cpu"
GAUDI_DIR="$PROJECT_ROOT/containers/vllm-gaudi"
GATEWAY_DIR="$PROJECT_ROOT/gateway"

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build and push Intel-RH AI Platform container images.

Required:
  --target TARGET       Build target: cpu, gaudi, gateway, or all

Options:
  --registry URL        Container registry (default: localhost)
  --tag TAG             Image tag (default: latest)
  --push                Push images to registry after building
  --dry-run             Show commands without executing
  --help                Show this help message

Examples:
  $(basename "$0") --target cpu
  $(basename "$0") --target gaudi --tag v2.0
  $(basename "$0") --target all --push --registry quay.io/my-org
  $(basename "$0") --target cpu --push --registry quay.io/my-org --dry-run

Image Names:
  CPU:   ${CPU_IMAGE}
  Gaudi: ${GAUDI_IMAGE}
EOF
}

check_prerequisites() {
    if command -v podman &>/dev/null; then
        CONTAINER_TOOL="podman"
    elif command -v docker &>/dev/null; then
        CONTAINER_TOOL="docker"
    else
        error "Neither podman nor docker found. Install one to build containers."
        exit 1
    fi
    info "Using container tool: $CONTAINER_TOOL"
}

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${BLUE}[DRY-RUN]${NC} $*"
    else
        info "Running: $*"
        "$@"
    fi
}

build_image() {
    local name="$1"
    local dir="$2"
    local containerfile="${3:-Containerfile}"
    local full_image="$REGISTRY/$name:$TAG"

    info "Building $name from $dir"

    if [ ! -f "$dir/$containerfile" ]; then
        error "Containerfile not found: $dir/$containerfile"
        return 1
    fi

    run_cmd "$CONTAINER_TOOL" build \
        -t "$full_image" \
        -f "$dir/$containerfile" \
        "$dir"

    info "Built: $full_image"
}

push_image() {
    local name="$1"
    local full_image="$REGISTRY/$name:$TAG"

    if [ "$REGISTRY" = "localhost" ]; then
        warn "Skipping push for localhost registry"
        return 0
    fi

    info "Pushing $full_image"
    run_cmd "$CONTAINER_TOOL" push "$full_image"
    info "Pushed: $full_image"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)   TARGET="$2"; shift 2 ;;
        --registry) REGISTRY="$2"; shift 2 ;;
        --tag)      TAG="$2"; shift 2 ;;
        --push)     PUSH=true; shift ;;
        --dry-run)  DRY_RUN=true; shift ;;
        --help|-h)  show_help; exit 0 ;;
        *)          error "Unknown option: $1"; show_help; exit 1 ;;
    esac
done

if [ -z "$TARGET" ]; then
    error "Missing required --target option"
    show_help
    exit 1
fi

if [ "$DRY_RUN" != true ]; then
    check_prerequisites
fi

case "$TARGET" in
    cpu)
        build_image "$CPU_IMAGE" "$CPU_DIR"
        if [ "$PUSH" = true ]; then push_image "$CPU_IMAGE"; fi
        ;;
    gaudi)
        build_image "$GAUDI_IMAGE" "$GAUDI_DIR"
        if [ "$PUSH" = true ]; then push_image "$GAUDI_IMAGE"; fi
        ;;
    gateway)
        build_image "inference-gateway" "$GATEWAY_DIR"
        if [ "$PUSH" = true ]; then push_image "inference-gateway"; fi
        ;;
    all)
        build_image "$CPU_IMAGE" "$CPU_DIR"
        build_image "$GAUDI_IMAGE" "$GAUDI_DIR"
        build_image "inference-gateway" "$GATEWAY_DIR"
        if [ "$PUSH" = true ]; then
            push_image "$CPU_IMAGE"
            push_image "$GAUDI_IMAGE"
            push_image "inference-gateway"
        fi
        ;;
    *)
        error "Invalid target: $TARGET (must be cpu, gaudi, gateway, or all)"
        exit 1
        ;;
esac

info "Done."
