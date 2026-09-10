#!/usr/bin/env bash
set -euo pipefail

# Reconcile Arena's permanent Cloudflare named tunnel and the Launchpad-owned
# public-access configuration. The tunnel token is an out-of-Git Secret. This
# workflow deliberately does not modify the OpenShift Console operator, its
# managed OAuthClient, or OAuth/cluster.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARENA_KUBECONFIG="${ARENA_KUBECONFIG:-/Users/jkershaw/.kube/config-arena}"
export KUBECONFIG="$ARENA_KUBECONFIG"

NAMESPACE="partner-ai-launchpad"
KEYCLOAK_NAMESPACE="keycloak"
KEYCLOAK_INTERNAL="http://keycloak-service.keycloak.svc:8080"
KEYCLOAK_ADMIN_URL="http://127.0.0.1:18087"
BACKEND_LOCAL_URL="http://127.0.0.1:18090"
BACKEND_ADMIN_URL="$BACKEND_LOCAL_URL/api/v1"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-https://labs.smg-helix.ai}"
ORDER_ID="${1:-}"

log() { printf '[arena-public-named] %s\n' "$*"; }
die() { printf '[arena-public-named] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "$KUBECONFIG" ]] || die "Arena kubeconfig not found: $KUBECONFIG"

infrastructure=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}') \
  || die "Arena API is unreachable; connect the VPN and retry"
[[ "$infrastructure" == arena-* ]] \
  || die "Refusing cluster '$infrastructure'; this workflow is Arena-only"

public_host=$(PUBLIC_ORIGIN="$PUBLIC_ORIGIN" python3 -c '
import os
from urllib.parse import urlsplit

origin = urlsplit(os.environ["PUBLIC_ORIGIN"])
if origin.scheme != "https" or origin.hostname != "labs.smg-helix.ai":
    raise SystemExit("PUBLIC_ORIGIN must be https://labs.smg-helix.ai")
if origin.path not in {"", "/"} or origin.query or origin.fragment or origin.username:
    raise SystemExit("PUBLIC_ORIGIN must be an HTTPS origin without path or credentials")
print(origin.hostname)
') || die "Invalid permanent public origin"

oc get secret tunnel-token -n "$NAMESPACE" >/dev/null \
  || die "Missing $NAMESPACE/tunnel-token; create it out of Git from the named-tunnel token"
oc get secret launchpad-public-access -n "$NAMESPACE" >/dev/null \
  || die "Missing $NAMESPACE/launchpad-public-access"

log "Applying the checked-in named tunnel and router"
oc apply -k "$SCRIPT_DIR" >/dev/null
oc rollout status deployment/cloudflare-tunnel -n "$NAMESPACE" --timeout=180s

log "Persisting Arena public placement and the permanent shared origin"
oc patch configmap launchpad-config -n "$NAMESPACE" --type=merge --patch "$(
  PUBLIC_ORIGIN="$PUBLIC_ORIGIN" PUBLIC_HOST="$public_host" python3 -c '
import json
import os

print(json.dumps({"data": {
    "PUBLIC_ACCESS_ENABLED": "true",
    "PUBLIC_LABS_DOMAIN": os.environ["PUBLIC_HOST"],
    "PUBLIC_LABS_SHARED_ORIGIN": os.environ["PUBLIC_ORIGIN"],
    "PUBLIC_LABS_SHARED_PATH_MODE": "true",
    "PUBLIC_ACCESS_PILOT_CLUSTER": "arena",
}}))
'
)" >/dev/null

cluster_config=$(oc get configmap launchpad-cluster-targets -n "$NAMESPACE" \
  -o jsonpath='{.data.clusters\.yaml}')
cluster_patch=$(CLUSTER_CONFIG="$cluster_config" PUBLIC_HOST="$public_host" python3 -c '
import json
import os

import yaml

config = yaml.safe_load(os.environ["CLUSTER_CONFIG"])
arena = [cluster for cluster in config.get("clusters", []) if cluster.get("cluster_id") == "arena"]
if len(arena) != 1:
    raise SystemExit("Expected exactly one Arena cluster target")
cluster = arena[0]
cluster["public_access_enabled"] = True
cluster["public_ingress_domain"] = os.environ["PUBLIC_HOST"]
cluster["public_console_url"] = ""
cluster["public_oauth_url"] = ""
print(json.dumps({"data": {"clusters.yaml": yaml.safe_dump(config, sort_keys=False)}}))
')
oc patch configmap launchpad-cluster-targets -n "$NAMESPACE" \
  --type=merge --patch "$cluster_patch" >/dev/null

for deployment in backend lifecycle-worker; do
  oc set env deployment/"$deployment" -n "$NAMESPACE" --containers="$deployment" \
    "PUBLIC_ACCESS_ENABLED=true" \
    "PUBLIC_LABS_DOMAIN=$public_host" \
    "PUBLIC_LABS_SHARED_ORIGIN=$PUBLIC_ORIGIN" \
    "PUBLIC_LABS_SHARED_PATH_MODE=true" \
    "PUBLIC_ACCESS_PILOT_CLUSTER=arena" >/dev/null
done
oc rollout status deployment/backend -n "$NAMESPACE" --timeout=180s
oc rollout status deployment/lifecycle-worker -n "$NAMESPACE" --timeout=180s

log "Persisting the permanent Keycloak frontend issuer"
keycloak_patch=$(PUBLIC_ORIGIN="$PUBLIC_ORIGIN" python3 -c '
import json
import os

print(json.dumps({"spec": {"hostname": {
    "hostname": os.environ["PUBLIC_ORIGIN"],
    "strict": True,
    "backchannelDynamic": True,
}}}))
')
oc patch keycloak keycloak -n "$KEYCLOAK_NAMESPACE" \
  --type=merge --patch "$keycloak_patch" >/dev/null
keycloak_generation=$(oc get keycloak keycloak -n "$KEYCLOAK_NAMESPACE" \
  -o jsonpath='{.metadata.generation}')
keycloak_ready="false"
for ((attempt=1; attempt<=90; attempt++)); do
  observed_generation=$(oc get keycloak keycloak -n "$KEYCLOAK_NAMESPACE" \
    -o jsonpath='{.status.observedGeneration}')
  ready_status=$(oc get keycloak keycloak -n "$KEYCLOAK_NAMESPACE" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
  if [[ "$observed_generation" == "$keycloak_generation" && "$ready_status" == "True" ]]; then
    keycloak_ready="true"
    break
  fi
  sleep 2
done
[[ "$keycloak_ready" == "true" ]] \
  || die "Keycloak did not reconcile the permanent hostname"
oc rollout status statefulset/keycloak -n "$KEYCLOAK_NAMESPACE" --timeout=300s

log "Configuring strict OIDC issuer validation with private back-channel endpoints"
oc set env deployment/public-access-gateway -n "$NAMESPACE" --containers=oidc-proxy \
  "OAUTH2_PROXY_OIDC_ISSUER_URL=$PUBLIC_ORIGIN/realms/launchpad-public" \
  "OAUTH2_PROXY_LOGIN_URL=$PUBLIC_ORIGIN/realms/launchpad-public/protocol/openid-connect/auth" \
  "OAUTH2_PROXY_REDEEM_URL=$KEYCLOAK_INTERNAL/realms/launchpad-public/protocol/openid-connect/token" \
  "OAUTH2_PROXY_OIDC_JWKS_URL=$KEYCLOAK_INTERNAL/realms/launchpad-public/protocol/openid-connect/certs" \
  "OAUTH2_PROXY_REDIRECT_URL=$PUBLIC_ORIGIN/oauth2/callback" \
  "OAUTH2_PROXY_SKIP_OIDC_DISCOVERY=true" \
  "OAUTH2_PROXY_INSECURE_OIDC_SKIP_ISSUER_VERIFICATION=false" >/dev/null
oc scale deployment/public-access-gateway --replicas=1 -n "$NAMESPACE" >/dev/null

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

log "Persisting the permanent launchpad-public realm frontend URL"
realm_json=$(curl -sf "$KEYCLOAK_ADMIN_URL/admin/realms/launchpad-public" \
  -H "Authorization: Bearer $keycloak_token")
updated_realm=$(printf '%s' "$realm_json" | PUBLIC_ORIGIN="$PUBLIC_ORIGIN" python3 -c '
import json
import os
import sys

realm = json.load(sys.stdin)
origin = os.environ["PUBLIC_ORIGIN"]
realm.setdefault("attributes", {})
realm["attributes"]["frontendUrl"] = origin
print(json.dumps(realm))
')
curl -sf -X PUT "$KEYCLOAK_ADMIN_URL/admin/realms/launchpad-public" \
  -H "Authorization: Bearer $keycloak_token" \
  -H 'Content-Type: application/json' \
  --data "$updated_realm" >/dev/null

internal_issuer=$(curl -fsS "$KEYCLOAK_ADMIN_URL/realms/launchpad-public/.well-known/openid-configuration" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("issuer", ""))')
[[ "$internal_issuer" == "$PUBLIC_ORIGIN/realms/launchpad-public" ]] \
  || die "Keycloak is issuing tokens from unexpected issuer '$internal_issuer'"

log "Persisting the permanent callback on the Launchpad gateway client"
gateway_client=$(curl -sf "$KEYCLOAK_ADMIN_URL/admin/realms/launchpad-public/clients?clientId=launchpad-public-gateway" \
  -H "Authorization: Bearer $keycloak_token")
gateway_client_id=$(printf '%s' "$gateway_client" \
  | python3 -c 'import json,sys; clients=json.load(sys.stdin); print(clients[0]["id"] if len(clients)==1 else "")')
[[ -n "$gateway_client_id" ]] || die "Expected exactly one launchpad-public-gateway client"
updated_client=$(printf '%s' "$gateway_client" | PUBLIC_ORIGIN="$PUBLIC_ORIGIN" python3 -c '
import json
import os
import sys

client = json.load(sys.stdin)[0]
origin = os.environ["PUBLIC_ORIGIN"]
client["redirectUris"] = [origin + "/oauth2/callback"]
client["webOrigins"] = [origin]
print(json.dumps(client))
')
curl -sf -X PUT "$KEYCLOAK_ADMIN_URL/admin/realms/launchpad-public/clients/$gateway_client_id" \
  -H "Authorization: Bearer $keycloak_token" \
  -H 'Content-Type: application/json' \
  --data "$updated_client" >/dev/null
unset keycloak_password keycloak_token realm_json updated_realm gateway_client updated_client

if [[ -n "$ORDER_ID" ]]; then
  log "Moving the existing order to the permanent origin without rotating its code"
  admin_key=$(oc get secret launchpad-api-keys -n "$NAMESPACE" \
    -o jsonpath='{.data.admin}' | base64 -d)
  curl -sf -X PATCH \
    "$BACKEND_ADMIN_URL/public-access/admin/orders/$ORDER_ID/public-url" \
    -H "X-API-Key: $admin_key" \
    -H 'Content-Type: application/json' \
    --data "{\"public_url\":\"$PUBLIC_ORIGIN\"}" >/dev/null
  unset admin_key
fi

oc rollout status deployment/public-access-gateway -n "$NAMESPACE" --timeout=180s

log "Verifying the permanent edge and OIDC discovery contract"
curl -fsS --retry 5 --retry-all-errors --retry-delay 2 "$PUBLIC_ORIGIN/health" >/dev/null
issuer=$(curl -fsS "$PUBLIC_ORIGIN/realms/launchpad-public/.well-known/openid-configuration" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("issuer", ""))')
[[ "$issuer" == "$PUBLIC_ORIGIN/realms/launchpad-public" ]] \
  || die "OIDC discovery returned unexpected issuer '$issuer'"

log "Permanent public origin ready: $PUBLIC_ORIGIN"
if [[ -n "$ORDER_ID" ]]; then
  log "The existing instructor code was not changed."
else
  log "Create a fresh public order for participant browser certification."
fi
log "OpenShift Console-through-tunnel remains outside this pilot gate."
