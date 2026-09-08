#!/usr/bin/env bash
set -euo pipefail

# Start the disposable Arena public-access pilot tunnel and configure only the
# Launchpad/Keycloak objects owned by this feature. The OpenShift Console
# operator, its managed OAuthClient, and the cluster OAuth configuration are
# deliberately left untouched.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARENA_KUBECONFIG="${ARENA_KUBECONFIG:-/Users/jkershaw/.kube/config-arena}"
export KUBECONFIG="$ARENA_KUBECONFIG"

NAMESPACE="partner-ai-launchpad"
ORDER_ID="${1:-}"
KEYCLOAK_NAMESPACE="keycloak"
KEYCLOAK_INTERNAL="http://keycloak-service.keycloak.svc:8080"
KEYCLOAK_ISSUER="https://keycloak.apps.arena.fm2aihpcsed.com/realms/launchpad-public"
KEYCLOAK_ADMIN_URL="http://127.0.0.1:18087"
BACKEND_LOCAL_URL="http://127.0.0.1:18090"
BACKEND_ADMIN_URL="$BACKEND_LOCAL_URL/api/v1"

log() { printf '[arena-public-pilot] %s\n' "$*"; }
die() { printf '[arena-public-pilot] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "$KUBECONFIG" ]] || die "Arena kubeconfig not found: $KUBECONFIG"

infrastructure=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}') \
  || die "Arena API is unreachable; connect the VPN and retry"
[[ "$infrastructure" == arena-* ]] \
  || die "Refusing cluster '$infrastructure'; this workflow is Arena-only"

console_operator_replicas=$(oc get deployment console-operator \
  -n openshift-console-operator -o jsonpath='{.spec.replicas}')
[[ "${console_operator_replicas:-0}" -gt 0 ]] \
  || die "Console operator is not running; restore the managed operator before starting the pilot"

idp_issuer=$(oc get oauth cluster -o json \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print(next((p.get("openID",{}).get("issuer","") for p in data.get("spec",{}).get("identityProviders",[]) if p.get("name")=="launchpad-public"), ""))')
[[ "$idp_issuer" == "$KEYCLOAK_ISSUER" ]] \
  || die "launchpad-public must use the stable Arena Keycloak issuer before tunnel startup"

log "Rendering the unprivileged tunnel router"
oc create configmap tunnel-router -n "$NAMESPACE" \
  --from-file=router.py="$SCRIPT_DIR/router.py" \
  --dry-run=client -o yaml | oc apply -f - >/dev/null
oc apply -f "$SCRIPT_DIR/deployment.yaml" >/dev/null
oc rollout restart deployment/cloudflare-tunnel -n "$NAMESPACE" >/dev/null
oc rollout status deployment/cloudflare-tunnel -n "$NAMESPACE" --timeout=180s

log "Waiting for the Cloudflare Quick Tunnel hostname"
tunnel_url=""
for ((attempt=1; attempt<=60; attempt++)); do
  tunnel_url=$(oc logs deployment/cloudflare-tunnel -c cloudflared -n "$NAMESPACE" \
    | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1 || true)
  [[ -n "$tunnel_url" ]] && break
  sleep 2
done
[[ -n "$tunnel_url" ]] || die "Cloudflare did not assign a pilot hostname"

log "Enabling the shared-origin public pilot on Arena"
oc set env deployment/backend -n "$NAMESPACE" --containers=backend \
  "PUBLIC_ACCESS_ENABLED=true" \
  "PUBLIC_LABS_SHARED_ORIGIN=$tunnel_url" \
  "PUBLIC_ACCESS_PILOT_CLUSTER=arena" >/dev/null
oc rollout status deployment/backend -n "$NAMESPACE" --timeout=180s

log "Configuring strict issuer validation with split browser/back-channel endpoints"
oc set env deployment/public-access-gateway -n "$NAMESPACE" --containers=oidc-proxy \
  "OAUTH2_PROXY_OIDC_ISSUER_URL=$KEYCLOAK_ISSUER" \
  "OAUTH2_PROXY_LOGIN_URL=$tunnel_url/realms/launchpad-public/protocol/openid-connect/auth" \
  "OAUTH2_PROXY_REDEEM_URL=$KEYCLOAK_INTERNAL/realms/launchpad-public/protocol/openid-connect/token" \
  "OAUTH2_PROXY_OIDC_JWKS_URL=$KEYCLOAK_INTERNAL/realms/launchpad-public/protocol/openid-connect/certs" \
  "OAUTH2_PROXY_REDIRECT_URL=$tunnel_url/oauth2/callback" \
  "OAUTH2_PROXY_SKIP_OIDC_DISCOVERY=true" \
  "OAUTH2_PROXY_INSECURE_OIDC_SKIP_ISSUER_VERIFICATION=false" >/dev/null
oc scale deployment/public-access-gateway --replicas=1 -n "$NAMESPACE" >/dev/null
oc rollout status deployment/public-access-gateway -n "$NAMESPACE" --timeout=180s

keycloak_forward_pid=""
backend_forward_pid=""
cleanup_forwards() {
  [[ -z "$keycloak_forward_pid" ]] || kill "$keycloak_forward_pid" 2>/dev/null || true
  [[ -z "$backend_forward_pid" ]] || kill "$backend_forward_pid" 2>/dev/null || true
}
trap cleanup_forwards EXIT
oc port-forward service/keycloak-service 18087:8080 -n "$KEYCLOAK_NAMESPACE" >/dev/null 2>&1 &
keycloak_forward_pid=$!
oc port-forward service/backend 18090:8000 -n "$NAMESPACE" >/dev/null 2>&1 &
backend_forward_pid=$!
for ((attempt=1; attempt<=30; attempt++)); do
  if curl -sf "$KEYCLOAK_ADMIN_URL/realms/master" >/dev/null \
    && curl -sf "$BACKEND_LOCAL_URL/health" >/dev/null; then
    break
  fi
  sleep 1
done
kill -0 "$keycloak_forward_pid" 2>/dev/null || die "Keycloak port-forward failed"
kill -0 "$backend_forward_pid" 2>/dev/null || die "Backend port-forward failed"

log "Updating the Keycloak gateway client without changing the Console client"
keycloak_user=$(oc get secret keycloak-bootstrap-admin -n "$KEYCLOAK_NAMESPACE" \
  -o jsonpath='{.data.username}' | base64 -d)
keycloak_password=$(oc get secret keycloak-bootstrap-admin -n "$KEYCLOAK_NAMESPACE" \
  -o jsonpath='{.data.password}' | base64 -d)
keycloak_token=$(curl -sf "$KEYCLOAK_ADMIN_URL/realms/master/protocol/openid-connect/token" \
  -d client_id=admin-cli \
  --data-urlencode "username=$keycloak_user" \
  --data-urlencode "password=$keycloak_password" \
  -d grant_type=password \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
gateway_client=$(curl -sf "$KEYCLOAK_ADMIN_URL/admin/realms/launchpad-public/clients?clientId=launchpad-public-gateway" \
  -H "Authorization: Bearer $keycloak_token")
gateway_client_id=$(printf '%s' "$gateway_client" \
  | python3 -c 'import json,sys; clients=json.load(sys.stdin); print(clients[0]["id"] if len(clients)==1 else "")')
[[ -n "$gateway_client_id" ]] || die "Expected exactly one launchpad-public-gateway client"
updated_client=$(printf '%s' "$gateway_client" | TUNNEL_URL="$tunnel_url" python3 -c '
import json, os, sys
client = json.load(sys.stdin)[0]
origin = os.environ["TUNNEL_URL"]
client["redirectUris"] = [origin + "/oauth2/callback"]
client["webOrigins"] = [origin]
print(json.dumps(client))
')
curl -sf -X PUT "$KEYCLOAK_ADMIN_URL/admin/realms/launchpad-public/clients/$gateway_client_id" \
  -H "Authorization: Bearer $keycloak_token" \
  -H 'Content-Type: application/json' \
  --data "$updated_client" >/dev/null

if [[ -n "$ORDER_ID" ]]; then
  log "Moving the existing order to the current pilot origin"
  admin_key=$(oc get secret launchpad-api-keys -n "$NAMESPACE" \
    -o jsonpath='{.data.admin}' | base64 -d)
  curl -sf -X PATCH \
    "$BACKEND_ADMIN_URL/public-access/admin/orders/$ORDER_ID/public-url" \
    -H "X-API-Key: $admin_key" \
    -H 'Content-Type: application/json' \
    --data "{\"public_url\":\"$tunnel_url\"}" >/dev/null
fi

log "Pilot URL: $tunnel_url"
if [[ -n "$ORDER_ID" ]]; then
  log "The existing instructor code was not changed."
else
  log "Create a public individual lab or workshop now; its URL will use this origin."
fi
log "This Quick Tunnel is disposable and does not certify production ingress."
