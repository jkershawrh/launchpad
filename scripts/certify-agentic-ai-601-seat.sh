#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-agentic-ai-601-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-agentic-ai-601-seat.sh <namespace> <cluster-id>}"
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

stage="workload-readiness"
oc --kubeconfig "$KUBECONFIG" rollout status deployment/agentic-ai-601-presentation \
  -n "$namespace" --timeout=300s >/dev/null
oc --kubeconfig "$KUBECONFIG" rollout status deployment/agentic-ai-601-qualifier \
  -n "$namespace" --timeout=300s >/dev/null

stage="route-discovery"
presentation_host="$(oc --kubeconfig "$KUBECONFIG" get route agentic-ai-601-presentation \
  -n "$namespace" -o jsonpath='{.spec.host}')"
qualifier_host="$(oc --kubeconfig "$KUBECONFIG" get route agentic-ai-601-qualifier \
  -n "$namespace" -o jsonpath='{.spec.host}')"
curl_options=(-fsSk --retry 4 --retry-all-errors --retry-delay 2 --max-time 180)
api="https://${qualifier_host}"

stage="presentation"
presentation="$(curl "${curl_options[@]}" "https://${presentation_host}/")"
grep -q 'Earn the Right to Act' <<<"$presentation"

stage="qualifier-health"
jq -e '.status == "ok"' <<<"$(curl "${curl_options[@]}" "${api}/healthz")" >/dev/null
jq -e '.status == "ready"' <<<"$(curl "${curl_options[@]}" "${api}/readyz")" >/dev/null
status="$(curl "${curl_options[@]}" "${api}/api/v1/status")"
jq -e '
  .sourceState == "rehearsal"
  and .executionAuthorityEnabled == false
  and .scope == "synthetic-lab-only"
  and .prerequisites.agentic401Certified == false
  and .prerequisites.agentic501Certified == false
' <<<"$status" >/dev/null

run_loop() {
  local correlation="$1" idempotency="$2" body="$3"
  curl "${curl_options[@]}" -X POST "${api}/api/v1/loop/run" \
    -H 'Content-Type: application/json' \
    -H "x-correlation-id: ${correlation}" \
    -H "idempotency-key: ${idempotency}" \
    --data-binary "$body"
}

stage="governed-loop"
observe="$(run_loop cert-observe cert-observe '{"scenario":"restart_required","requestedStage":"observe","namespace":"agentic-ai-601-lab-cert"}')"
jq -e '.sourceState == "rehearsal" and .signal.conditionClass == "synthetic.pod_unhealthy" and .action.attempts == 0' <<<"$observe" >/dev/null

unapproved="$(run_loop cert-unapproved cert-unapproved '{"scenario":"restart_required","requestedStage":"bounded_action","namespace":"agentic-ai-601-lab-cert"}')"
jq -e '.decision.reason == "human_approval_required" and .action.attempts == 0' <<<"$unapproved" >/dev/null

approved_body='{"scenario":"restart_required","requestedStage":"bounded_action","namespace":"agentic-ai-601-lab-cert","approvalToken":"approval-cert-single-use","simulation":true}'
approved="$(run_loop cert-approved cert-approved "$approved_body")"
reused="$(run_loop cert-reused cert-reused "$approved_body")"
jq -e '.decision.disposition == "simulate" and .action.executed == true and .action.attempts == 1' <<<"$approved" >/dev/null
jq -e '.decision.reason == "approval_token_already_used" and .action.attempts == 0' <<<"$reused" >/dev/null

replay_first="$(run_loop cert-replay cert-replay '{"scenario":"restart_required","requestedStage":"recommend","namespace":"agentic-ai-601-lab-cert"}')"
replay_second="$(run_loop cert-replay-duplicate cert-replay '{"scenario":"restart_required","requestedStage":"recommend","namespace":"agentic-ai-601-lab-cert"}')"
test "$(jq -r '.recordId' <<<"$replay_first")" = "$(jq -r '.recordId' <<<"$replay_second")"

failure="$(run_loop cert-failure cert-failure '{"scenario":"validation_failure","requestedStage":"bounded_action","namespace":"agentic-ai-601-lab-cert","approvalToken":"approval-cert-failure","simulation":true}')"
jq -e '.validation.passed == false and .validation.rollbackTriggered == true and .validation.rollbackPassed == true and .learning.demotionTriggered == true' <<<"$failure" >/dev/null

kill_switch="$(run_loop cert-kill cert-kill '{"scenario":"kill_switch","requestedStage":"bounded_action","namespace":"agentic-ai-601-lab-cert","approvalToken":"approval-cert-kill","simulation":true}')"
jq -e '.decision.reason == "emergency_stop_active" and .action.attempts == 0 and .learning.demotionTriggered == true' <<<"$kill_switch" >/dev/null

chain="$(curl "${curl_options[@]}" "${api}/api/v1/evidence/verify")"
jq -e '.valid == true' <<<"$chain" >/dev/null

stage="terminal-scope"
terminal_scope="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom \
  -c terminal -- sh -c '
    printf "project=%s\n" "$(oc project -q)"
    printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")"
    if oc get pods -n launchpad-flightpath-candidate >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
    if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
  ')"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx 'own_edit=yes' <<<"$terminal_scope"
grep -qx 'cross_namespace=DENIED' <<<"$terminal_scope"
grep -qx 'node_list=DENIED' <<<"$terminal_scope"

stage="evidence"
jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg presentation_host "$presentation_host" \
  --arg qualifier_host "$qualifier_host" \
  --arg terminal_scope "$terminal_scope" \
  '{
    result: "GREEN-destination-rehearsal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    source_state: "rehearsal",
    execution_authority_enabled: false,
    readiness: {presentation: true, qualifier: true, routes: true},
    presentation_host: $presentation_host,
    qualifier_host: $qualifier_host,
    governed_loop: {
      signal_observed: true,
      unapproved_action_denied: true,
      single_use_approval_enforced: true,
      idempotent_replay: true,
      rollback_and_demotion: true,
      emergency_stop_precedes_action: true,
      evidence_chain_valid: true,
      automated_promotion: false,
      human_review_required: true
    },
    terminal_scope: ($terminal_scope | split("\n")),
    contains_sensitive_values: false
  }'
