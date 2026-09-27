#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SHOWROOM_MARKER="Operate Evidence-Backed Multi-Agent Systems"
export PRESENTATION_REQUIRED=true

exec "$script_dir/certify-multi-agent-seat.sh" "$@"
