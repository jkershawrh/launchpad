#!/usr/bin/env bash
set -euo pipefail
namespace="${1:?usage: certify-ai-sandbox-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-ai-sandbox-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the execution cluster credential}"
stage=cluster-identity
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
oc() { command oc --kubeconfig "$KUBECONFIG" "$@"; }

actual_cluster="$(oc get namespace "$namespace" -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}')"
[[ "$actual_cluster" == "$expected_cluster" ]]

stage=workspace-readiness
oc rollout status deployment/sandbox -n "$namespace" --timeout=300s >/dev/null
home_writable="$(oc exec -n "$namespace" deployment/sandbox -- sh -c 'test -w /home/lab-user/workspace && echo true || echo false')"
[[ "$home_writable" == true ]]

stage=ide-route
ide_host="$(oc get route sandbox-vscode -n "$namespace" -o jsonpath='{.spec.host}')"
ide_status=000
for _ in {1..20}; do
  ide_status="$(curl -kLsS -o /dev/null -w '%{http_code}' "https://${ide_host}/" || true)"
  [[ "$ide_status" == 200 ]] && break
  sleep 2
done
[[ "$ide_status" == 200 ]]

stage=model-endpoint
model_status="$(oc exec -n "$namespace" deployment/sandbox -- sh -c '
  test -n "$LITELLM_API_BASE" && test -n "$LITELLM_API_KEY"
  curl -fsS -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $LITELLM_API_KEY" "${LITELLM_API_BASE%/}/v1/models"
')"
[[ "$model_status" == 200 ]]

stage=terminal-scope
terminal_scope="$(oc exec -n "$namespace" deployment/sandbox -- sh -c '
  printf "project=%s\n" "$(oc project -q)"
  printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$SANDBOX_NAMESPACE")"
  if oc get pods -n partner-ai-launchpad >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
  if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
')"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx own_edit=yes <<<"$terminal_scope"
grep -qx cross_namespace=DENIED <<<"$terminal_scope"
grep -qx node_list=DENIED <<<"$terminal_scope"

jq -cn --arg namespace "$namespace" --arg cluster_ref "$expected_cluster" \
  --argjson ide_status "$ide_status" --argjson model_status "$model_status" \
  --argjson home_writable "$home_writable" --arg terminal_scope "$terminal_scope" '{
    result:"GREEN-live-internal-seat",namespace:$namespace,cluster_ref:$cluster_ref,
    workspace:{deployment_ready:true,ide_http_status:$ide_status,home_writable:$home_writable},
    model:{models_http_status:$model_status},
    terminal_scope:($terminal_scope | split("\n")),contains_sensitive_values:false
  }'
