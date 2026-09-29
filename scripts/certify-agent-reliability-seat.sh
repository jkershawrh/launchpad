#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-agent-reliability-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-agent-reliability-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

stage="setup"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
probe_binding="launchpad-certification-probe"
probe_serviceaccount="${LAUNCHPAD_CERTIFICATION_SERVICEACCOUNT:-partner-ai-launchpad:launchpad-provisioner}"
cleanup_probe_access() {
  oc --kubeconfig "$KUBECONFIG" delete rolebinding "$probe_binding" \
    --namespace "$namespace" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup_probe_access EXIT
oc --kubeconfig "$KUBECONFIG" create rolebinding "$probe_binding" \
  --clusterrole=edit \
  --serviceaccount="$probe_serviceaccount" \
  --namespace "$namespace" --dry-run=client -o yaml \
  | oc --kubeconfig "$KUBECONFIG" apply -f - >/dev/null

stage="route-discovery"
workspace_host="$(oc --kubeconfig "$KUBECONFIG" get route ar -n "$namespace" -o jsonpath='{.spec.host}')"
curl_options=(-fsSk --retry 3 --retry-all-errors --retry-delay 2 --max-time 180)
stage="health"
health="$(curl "${curl_options[@]}" "https://${workspace_host}/health")"
jq -e '.status == "healthy" and .failure_injection == true' <<<"$health" >/dev/null
stage="workspace"
workspace="$(curl "${curl_options[@]}" "https://${workspace_host}/")"
grep -q 'Agent Reliability Advisor' <<<"$workspace"

request() {
  local failure="$1"
  curl "${curl_options[@]}" -X POST "https://${workspace_host}/api/v1/advise" \
    -H 'Content-Type: application/json' \
    --data "{\"query\":\"Diagnose NOC-1042 and recommend the safest next step\",\"failure\":\"${failure}\"}"
}

stage="healthy-journey"
healthy="$(request none)"
jq -e '
  .outcome == "recommended"
  and .model_status == "available"
  and (.evidence | length) == 3
  and .human_approval_required == true
  and (.trace_id | type) == "string"
' <<<"$healthy" >/dev/null
stage="prompt-injection"
prompt_injection="$(request prompt_injection)"
jq -e '.outcome == "abstained" and .model_status == "not_called" and (.executed_tools | length) == 0' <<<"$prompt_injection" >/dev/null
stage="unauthorized-tool"
unauthorized="$(request unauthorized_tool)"
jq -e '.outcome == "denied" and .model_status == "not_called" and (.executed_tools | length) == 0' <<<"$unauthorized" >/dev/null
stage="inference-timeout"
timeout_result="$(request inference_timeout)"
jq -e '.outcome == "degraded" and .model_status == "unavailable" and .human_approval_required == true' <<<"$timeout_result" >/dev/null

stage="terminal-scope"
terminal_scope="$(
  oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom \
    -c terminal -- sh -c '
      printf "project=%s\n" "$(oc project -q)"
      printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")"
      if oc get pods -n launchpad-flightpath-candidate >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
      if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
    '
)"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx 'own_edit=yes' <<<"$terminal_scope"
grep -qx 'cross_namespace=DENIED' <<<"$terminal_scope"
grep -qx 'node_list=DENIED' <<<"$terminal_scope"

stage="runtime-contract"
runtime_keys="$(oc --kubeconfig "$KUBECONFIG" get secret model-connection -n "$namespace" -o json | jq -c '.data | keys | sort')"
[[ "$runtime_keys" == '["api-key","endpoint","model"]' ]]

stage="evidence"
jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg terminal_scope "$terminal_scope" \
  --arg healthy_guardrail "$(jq -r '.policy_decisions[] | select(.control == "input-guardrail") | .provider' <<<"$healthy")" \
  --argjson runtime_keys "$runtime_keys" \
  '{
    result: "GREEN-live-internal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    readiness: {health: true, workspace_http_status: 200},
    reliability_journey: {
      healthy: "recommended",
      prompt_injection: "abstained",
      unauthorized_tool: "denied",
      inference_timeout: "degraded",
      evidence_records: 3,
      human_approval_required: true,
      guardrail_provider: $healthy_guardrail
    },
    terminal_scope: ($terminal_scope | split("\n")),
    runtime_secret_keys: $runtime_keys,
    contains_sensitive_values: false
  }'
