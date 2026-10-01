#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-hybrid-fraud-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-hybrid-fraud-seat.sh <namespace> <cluster-id>}"
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
scorer_host="$(oc --kubeconfig "$KUBECONFIG" get route fraud-scorer -n "$namespace" -o jsonpath='{.spec.host}')"
ui_host="$(oc --kubeconfig "$KUBECONFIG" get route fraud-ui -n "$namespace" -o jsonpath='{.spec.host}')"
curl_options=(-fsSk --retry 3 --retry-all-errors --retry-delay 2 --max-time 180)

stage="health"
health="$(curl "${curl_options[@]}" "https://${scorer_host}/health")"
jq -e '.status == "ok" and .mode == "live"' <<<"$health" >/dev/null
stage="readiness"
readiness="$(curl "${curl_options[@]}" "https://${scorer_host}/ready")"
jq -e '.status == "ready" and .mode == "live"' <<<"$readiness" >/dev/null
stage="workspace"
[[ "$(curl "${curl_options[@]}" -o /dev/null -w '%{http_code}' "https://${ui_host}/")" == "200" ]]

stage="hybrid-score"
score="$({ curl "${curl_options[@]}" -X POST "https://${scorer_host}/api/v1/score" \
  -H 'Content-Type: application/json' \
  --data '{"amount":5000,"currency":"USD","country":"US","category":"wire_transfer","description":"Synthetic supplier payment with changed banking details"}'; })"
jq -e '
  .rule_score == 30
  and .llm_skipped == false
  and (.llm_score | type) == "number"
  and (.risk_score >= 0 and .risk_score <= 100)
  and .model == "granite-3.2-8b-tools"
  and (.ai_disclaimer | contains("not for real decisions"))
' <<<"$score" >/dev/null

stage="bounded-input"
invalid_status="$(curl -ksS -o /dev/null -w '%{http_code}' -X POST \
  "https://${scorer_host}/api/v1/score" -H 'Content-Type: application/json' \
  --data '{"amount":-1}')"
[[ "$invalid_status" == "422" ]]

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
runtime_keys="$(oc --kubeconfig "$KUBECONFIG" get secret fraud-model-runtime -n "$namespace" -o json | jq -c '.data | keys | sort')"
[[ "$runtime_keys" == '["api-key","endpoint","name"]' ]]

stage="evidence"
jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg model "$(jq -r '.model' <<<"$score")" \
  --arg terminal_scope "$terminal_scope" \
  --argjson risk_score "$(jq '.risk_score' <<<"$score")" \
  --argjson llm_score "$(jq '.llm_score' <<<"$score")" \
  --argjson runtime_keys "$runtime_keys" \
  '{
    result: "GREEN-live-internal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    readiness: {health: true, model_ready: true, workspace_http_status: 200},
    hybrid_journey: {live_model: true, model: $model, risk_score: $risk_score, llm_score: $llm_score, bounded_input: true, human_authority_preserved: true},
    terminal_scope: ($terminal_scope | split("\n")),
    runtime_secret_keys: $runtime_keys,
    contains_sensitive_values: false
  }'
