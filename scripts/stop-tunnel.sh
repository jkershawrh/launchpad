#!/usr/bin/env bash
set -euo pipefail

ARENA_KUBECONFIG="${ARENA_KUBECONFIG:-/Users/jkershaw/.kube/config-arena}"
export KUBECONFIG="$ARENA_KUBECONFIG"
NAMESPACE="partner-ai-launchpad"

infrastructure=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}') \
  || { printf 'Arena API is unreachable; connect the VPN and retry\n' >&2; exit 1; }
[[ "$infrastructure" == arena-* ]] \
  || { printf "Refusing cluster '%s'; this workflow is Arena-only\n" "$infrastructure" >&2; exit 1; }

oc set env deployment/backend -n "$NAMESPACE" --containers=backend \
  PUBLIC_ACCESS_ENABLED- \
  PUBLIC_LABS_SHARED_ORIGIN- \
  PUBLIC_ACCESS_PILOT_CLUSTER- >/dev/null
oc scale deployment/public-access-gateway --replicas=0 -n "$NAMESPACE" >/dev/null
oc scale deployment/cloudflare-tunnel --replicas=0 -n "$NAMESPACE" >/dev/null
oc rollout status deployment/backend -n "$NAMESPACE" --timeout=180s
printf 'Arena public pilot stopped and public ordering failed closed. Console and authentication operators were not modified.\n'
