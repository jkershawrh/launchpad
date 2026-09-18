#!/usr/bin/env bash
set -euo pipefail

# One-time setup for a Cloudflare Named Tunnel
# This gives a stable hostname that survives cloudflared restarts,
# eliminating the need to update OAuthClient/Keycloak/gateway/DB
# every time the tunnel process restarts.
#
# Prerequisites: a free Cloudflare account (https://dash.cloudflare.com/sign-up)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

TUNNEL_NAME="${1:-launchpad-arena}"

log() { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[setup]\033[0m %s\n' "$*" >&2; }
die() { err "$@"; exit 1; }

which cloudflared >/dev/null 2>&1 || which ~/.local/bin/cloudflared >/dev/null 2>&1 \
    || die "cloudflared not found. Install: brew install cloudflared"
CF=$(which cloudflared 2>/dev/null || echo "$HOME/.local/bin/cloudflared")

# Step 1: Authenticate (opens browser)
if [[ ! -f "$HOME/.cloudflared/cert.pem" ]]; then
    log "Step 1: Authenticating with Cloudflare (opens browser)..."
    "$CF" tunnel login
else
    log "Step 1: Already authenticated (cert.pem exists)"
fi

# Step 2: Create the named tunnel
log "Step 2: Creating tunnel '$TUNNEL_NAME'..."
EXISTING=$("$CF" tunnel list --output json 2>/dev/null | python3 -c "
import json, sys
tunnels = json.loads(sys.stdin.read())
for t in tunnels:
    if t['name'] == '$TUNNEL_NAME':
        print(t['id'])
        break
" 2>/dev/null || echo "")

if [[ -n "$EXISTING" ]]; then
    log "Tunnel '$TUNNEL_NAME' already exists (ID: $EXISTING)"
    TUNNEL_ID="$EXISTING"
else
    TUNNEL_ID=$("$CF" tunnel create "$TUNNEL_NAME" 2>&1 | grep -oP 'Created tunnel .+ with id \K[a-f0-9-]+' || true)
    if [[ -z "$TUNNEL_ID" ]]; then
        err "Failed to create tunnel. Output:"
        "$CF" tunnel create "$TUNNEL_NAME" 2>&1
        die "Tunnel creation failed"
    fi
    log "Created tunnel ID: $TUNNEL_ID"
fi

# Step 3: Write config
CONFIG_FILE="$PROJECT_DIR/.cloudflared-config.yml"
cat > "$CONFIG_FILE" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/$TUNNEL_ID.json
ingress:
  - service: http://127.0.0.1:18086
EOF

log "Wrote config to $CONFIG_FILE"

# Step 4: Get the hostname
TUNNEL_HOST="${TUNNEL_ID}.cfargotunnel.com"
log ""
log "============================================"
log "Named tunnel ready!"
log "============================================"
log "Tunnel name:  $TUNNEL_NAME"
log "Tunnel ID:    $TUNNEL_ID"
log "Hostname:     $TUNNEL_HOST"
log "Config:       $CONFIG_FILE"
log ""
log "This hostname is STABLE. Once you configure"
log "OAuthClient, Keycloak, gateway, and DB with"
log "this hostname, you never need to update them"
log "again (even if cloudflared restarts)."
log ""
log "start-tunnel.sh will auto-detect this config"
log "and use the named tunnel instead of Quick Tunnel."
log "============================================"
