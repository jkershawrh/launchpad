#!/usr/bin/env bash
set -euo pipefail

ARENA_KUBECONFIG="${ARENA_KUBECONFIG:-/Users/jkershaw/.kube/config-arena}"
export KUBECONFIG="$ARENA_KUBECONFIG"
NAMESPACE="partner-ai-launchpad"
CONSOLE_ROUTE_BACKUP="launchpad-public-console-route-backup"
CONSOLE_ROUTE_SECRET="launchpad-public-console-route-tls"

infrastructure=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}') \
  || { printf 'Arena API is unreachable; connect the VPN and retry\n' >&2; exit 1; }
[[ "$infrastructure" == arena-* ]] \
  || { printf "Refusing cluster '%s'; this workflow is Arena-only\n" "$infrastructure" >&2; exit 1; }

if oc get configmap "$CONSOLE_ROUTE_BACKUP" -n "$NAMESPACE" >/dev/null 2>&1; then
  original_console_route=$(oc get configmap "$CONSOLE_ROUTE_BACKUP" -n "$NAMESPACE" \
    -o jsonpath='{.data.route\.json}')
  restore_patch=$(printf '%s' "$original_console_route" | python3 -c '
import json, sys
route = json.load(sys.stdin)
print(json.dumps([{"op": "replace", "path": "/spec/route", "value": route}]))
')
  oc patch consoles.operator.openshift.io cluster --type=json -p "$restore_patch" >/dev/null
  for ((attempt=1; attempt<=60; attempt++)); do
    current_host=$(oc get consoles.operator.openshift.io cluster -o jsonpath='{.spec.route.hostname}')
    [[ "$current_host" == "$(printf '%s' "$original_console_route" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("hostname", ""))')" ]] && break
    sleep 2
  done
  oc delete secret "$CONSOLE_ROUTE_SECRET" -n openshift-config --ignore-not-found >/dev/null
  oc delete configmap "$CONSOLE_ROUTE_BACKUP" -n "$NAMESPACE" --ignore-not-found >/dev/null
fi

oc set env deployment/backend -n "$NAMESPACE" --containers=backend \
  PUBLIC_ACCESS_ENABLED- \
  PUBLIC_LABS_SHARED_ORIGIN- \
  PUBLIC_ACCESS_PILOT_CLUSTER- >/dev/null
oc scale deployment/public-access-gateway --replicas=0 -n "$NAMESPACE" >/dev/null
oc scale deployment/cloudflare-tunnel --replicas=0 -n "$NAMESPACE" >/dev/null
oc rollout status deployment/backend -n "$NAMESPACE" --timeout=180s
printf 'Arena public pilot stopped, public ordering failed closed, and the prior Console route was restored.\n'
