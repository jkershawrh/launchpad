#!/usr/bin/env bash
#
# export-models.sh - Export HuggingFace models to OpenVINO IR format
#
# Exports models optimized for Xeon 6 AMX acceleration with INT8/BF16.
# Requires: pip install optimum[openvino]
#
# Usage:
#   ./export-models.sh --model embeddings    # Export embedding model
#   ./export-models.sh --model reranker      # Export reranker model
#   ./export-models.sh --model classifier    # Export classifier model
#   ./export-models.sh --model all           # Export all models
#   ./export-models.sh --output-dir ./models # Custom output directory
#   ./export-models.sh --dry-run             # Show commands only
#   ./export-models.sh --help

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

MODEL=""
OUTPUT_DIR="$PROJECT_ROOT/models/openvino"
DRY_RUN=false
WEIGHT_FORMAT="int8"

# Model definitions
EMBEDDINGS_MODEL="sentence-transformers/all-MiniLM-L6-v2"
EMBEDDINGS_TASK="feature-extraction"

RERANKER_MODEL="cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_TASK="text-classification"

CLASSIFIER_MODEL="distilbert-base-uncased-finetuned-sst-2-english"
CLASSIFIER_TASK="text-classification"

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Export HuggingFace models to OpenVINO IR format for Xeon 6 deployment.

Required:
  --model MODEL         Model to export: embeddings, reranker, classifier, or all

Options:
  --output-dir DIR      Output directory (default: models/openvino/)
  --weight-format FMT   Weight format: fp32, fp16, int8 (default: int8 for AMX)
  --dry-run             Show commands without executing
  --help                Show this help

Models:
  embeddings   $EMBEDDINGS_MODEL (sentence embeddings)
  reranker     $RERANKER_MODEL (cross-encoder reranking)
  classifier   $CLASSIFIER_MODEL (sentiment classification)

The exported models can be served directly by OpenVINO Model Server on OpenShift AI.
INT8 weight format enables AMX acceleration on Xeon 6 (Granite Rapids).
EOF
}

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${BLUE}[DRY-RUN]${NC} $*"
    else
        info "Running: $*"
        "$@"
    fi
}

export_model() {
    local name="$1"
    local hf_model="$2"
    local task="$3"
    local out="$OUTPUT_DIR/$name"

    info "Exporting $name: $hf_model (task: $task, format: $WEIGHT_FORMAT)"

    run_cmd optimum-cli export openvino \
        --model "$hf_model" \
        --task "$task" \
        --weight-format "$WEIGHT_FORMAT" \
        "$out"

    info "Exported to: $out"
}

check_prerequisites() {
    if ! command -v optimum-cli &>/dev/null; then
        error "optimum-cli not found. Install with: pip install optimum[openvino]"
        exit 1
    fi
    info "Using optimum-cli: $(which optimum-cli)"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)         MODEL="$2"; shift 2 ;;
        --output-dir)    OUTPUT_DIR="$2"; shift 2 ;;
        --weight-format) WEIGHT_FORMAT="$2"; shift 2 ;;
        --dry-run)       DRY_RUN=true; shift ;;
        --help|-h)       show_help; exit 0 ;;
        *)               error "Unknown option: $1"; show_help; exit 1 ;;
    esac
done

if [ -z "$MODEL" ]; then
    error "Missing required --model option"
    show_help
    exit 1
fi

if [ "$DRY_RUN" != true ]; then
    check_prerequisites
    mkdir -p "$OUTPUT_DIR"
fi

case "$MODEL" in
    embeddings)
        export_model "all-MiniLM-L6-v2" "$EMBEDDINGS_MODEL" "$EMBEDDINGS_TASK"
        ;;
    reranker)
        export_model "ms-marco-MiniLM-L-6-v2" "$RERANKER_MODEL" "$RERANKER_TASK"
        ;;
    classifier)
        export_model "distilbert-sst2" "$CLASSIFIER_MODEL" "$CLASSIFIER_TASK"
        ;;
    all)
        export_model "all-MiniLM-L6-v2" "$EMBEDDINGS_MODEL" "$EMBEDDINGS_TASK"
        export_model "ms-marco-MiniLM-L-6-v2" "$RERANKER_MODEL" "$RERANKER_TASK"
        export_model "distilbert-sst2" "$CLASSIFIER_MODEL" "$CLASSIFIER_TASK"
        ;;
    *)
        error "Invalid model: $MODEL (must be embeddings, reranker, classifier, or all)"
        exit 1
        ;;
esac

info "Done."
