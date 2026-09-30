#!/usr/bin/env bash
set -euo pipefail

# The 301 experience now includes its own Story presentation and requires
# end-to-end correlation across the progressive workflow. Keep those gates
# mandatory instead of relying on the generic driver's optional defaults.
export PRESENTATION_REQUIRED=true
export CORRELATION_REQUIRED=true

exec bash "$(dirname "$0")/certify-multi-agent-seat.sh" "$@"
