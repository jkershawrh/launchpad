#!/usr/bin/env bash
set -euo pipefail

# Compatibility helper retained for callers that previously scraped a
# disposable hostname. The public hostname is permanent now; apply.sh owns all
# configuration reconciliation.

PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-https://labs.smg-helix.ai}"
[[ "$PUBLIC_ORIGIN" == "https://labs.smg-helix.ai" ]] || {
  printf 'Unexpected public origin: %s\n' "$PUBLIC_ORIGIN" >&2
  exit 1
}
printf '%s\n' "$PUBLIC_ORIGIN"
