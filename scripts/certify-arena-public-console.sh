#!/usr/bin/env bash
# Prepare Arena's supported custom Console route and optionally enable one
# public order. This is deliberately separate from start-tunnel.sh because it
# changes cluster-wide Console routing and must remain an explicit canary gate.

set -euo pipefail

ARENA_KUBECONFIG="${ARENA_KUBECONFIG:-/Users/jkershaw/.kube/config-arena}"
PUBLIC_HOST="${PUBLIC_HOST:-labs.smg-helix.ai}"
CONSOLE_TLS_SECRET="${CONSOLE_TLS_SECRET:-launchpad-public-console-route-tls}"
LAUNCHPAD_NAMESPACE="${LAUNCHPAD_NAMESPACE:-partner-ai-launchpad}"
BACKUP_CONFIGMAP="launchpad-public-console-route-backup"

usage() {
  echo "Usage: $0 prepare | enable-order <order-id> | disable-order <order-id> | status" >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
action="$1"
order_id="${2:-}"

oc_arena() {
  oc --kubeconfig "$ARENA_KUBECONFIG" "$@"
}

api_server=$(oc_arena whoami --show-server)
[[ "$api_server" == "https://api.arena.fm2aihpcsed.com:6443" ]] || {
  echo "Refusing non-Arena API server: $api_server" >&2
  exit 1
}

set_order_flag() {
  local enabled="$1"
  [[ -n "$order_id" ]] || usage
  oc_arena -n "$LAUNCHPAD_NAMESPACE" exec deploy/backend -- \
    sh -ceu '
      order_id="$1"
      enabled="$2"
      key="${ADMIN_API_KEYS%%,*}"
      test -n "$key"
      curl -fsS -X PATCH \
        -H "X-API-Key: $key" \
        -H "Content-Type: application/json" \
        -d "{\"enabled\":$enabled}" \
        "http://127.0.0.1:8000/api/v1/public-access/admin/orders/$order_id/console"
    ' sh "$order_id" "$enabled"
  echo
}

prepare_console() {
  oc_arena -n openshift-config get secret "$CONSOLE_TLS_SECRET" >/dev/null || {
    echo "Missing openshift-config/$CONSOLE_TLS_SECRET; install a private-key Secret outside Git first." >&2
    exit 1
  }

  if ! oc_arena -n "$LAUNCHPAD_NAMESPACE" get configmap "$BACKUP_CONFIGMAP" >/dev/null 2>&1; then
    original_route=$(oc_arena get console.operator.openshift.io cluster -o jsonpath='{.spec.route}')
    [[ -n "$original_route" ]] || original_route='{}'
    oc_arena -n "$LAUNCHPAD_NAMESPACE" create configmap "$BACKUP_CONFIGMAP" \
      --from-literal="route-json=$original_route"
  fi

  patch=$(printf '{"spec":{"route":{"hostname":"%s","secret":{"name":"%s"}}}}' \
    "$PUBLIC_HOST" "$CONSOLE_TLS_SECRET")
  oc_arena patch console.operator.openshift.io cluster --type=merge -p "$patch"
  oc_arena wait clusteroperator/console --for=condition=Available=True --timeout=180s

  degraded=$(oc_arena get clusteroperator console -o jsonpath='{.status.conditions[?(@.type=="Degraded")].status}')
  [[ "$degraded" == "False" ]] || {
    echo "Console operator is degraded after custom-route activation" >&2
    exit 1
  }
  route_host=$(oc_arena -n openshift-console get route console-custom -o jsonpath='{.spec.host}')
  [[ "$route_host" == "$PUBLIC_HOST" ]] || {
    echo "Unexpected Console custom Route host: $route_host" >&2
    exit 1
  }
  redirect=$(oc_arena get oauthclient console -o jsonpath='{.redirectURIs[0]}')
  [[ "$redirect" == "https://$PUBLIC_HOST/auth/callback" ]] || {
    echo "Unexpected operator-managed Console callback: $redirect" >&2
    exit 1
  }
}

case "$action" in
  prepare)
    [[ $# -eq 1 ]] || usage
    prepare_console
    ;;
  enable-order)
    [[ $# -eq 2 ]] || usage
    prepare_console
    set_order_flag true
    ;;
  disable-order)
    [[ $# -eq 2 ]] || usage
    set_order_flag false
    ;;
  status)
    [[ $# -eq 1 ]] || usage
    oc_arena get clusteroperator console authentication
    oc_arena -n openshift-console get route console-custom
    ;;
  *)
    usage
    ;;
esac
