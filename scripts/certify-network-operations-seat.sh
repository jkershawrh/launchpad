#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-network-operations-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-network-operations-seat.sh <namespace> <cluster-id>}"
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
app_host="$(oc --kubeconfig "$KUBECONFIG" get route netops -n "$namespace" -o jsonpath='{.spec.host}')"
# The participant-facing workspace and story paths are allowed to normalize a
# missing trailing slash. Browsers follow that redirect, so the certification
# probe must validate the final page instead of treating the safe redirect as a
# functional failure.
curl_options=(-fsSkL --retry 3 --retry-all-errors --retry-delay 2 --max-time 180)
http_status_options=(-sSkL --retry 3 --retry-all-errors --retry-delay 2 --max-time 180)

stage="health"
health="$(curl "${curl_options[@]}" "https://${app_host}/health")"
jq -e '.status == "ok" and .lab_mode == true' <<<"$health" >/dev/null
stage="readiness"
readiness="$(curl "${curl_options[@]}" "https://${app_host}/ready")"
jq -e '.status == "ready"' <<<"$readiness" >/dev/null
stage="workspace-http"
# The Showroom/public gateway exposes this tool at /workspace and rewrites that
# same-origin path to the workload Route root. Probe the actual workload root
# here; probing /workspace directly bypasses the gateway rewrite and is a 404.
workspace_status="$(curl "${http_status_options[@]}" -o /dev/null -w '%{http_code}' "https://${app_host}/")"
if [[ "$workspace_status" != "200" ]]; then
  printf 'semantic_response=workspace_http_status:%s\n' "$workspace_status" >&2
  false
fi
stage="story-http"
story_status="$(curl "${http_status_options[@]}" -o /dev/null -w '%{http_code}' "https://${app_host}/story/")"
if [[ "$story_status" != "200" ]]; then
  printf 'semantic_response=story_http_status:%s\n' "$story_status" >&2
  false
fi

stage="live-investigation"
investigation="$({ curl "${curl_options[@]}" -X POST "https://${app_host}/api/investigate" \
  -H 'Content-Type: application/json' --data '{"scenario_id":"ptp-hardware"}'; })"
jq -e '
  .primary_hypothesis.cause == "hardware_timing"
  and .action_requires_human_approval == true
  and .action_executed == false
  and (.current_observations_with_tool_provenance | length) == 3
  and .model_draft.status == "unverified_draft_for_human_review"
  and (.model_draft.model | type) == "string"
' <<<"$investigation" >/dev/null

stage="qualification"
scenario='{"schema_version":"network-operations-agent.lab-scenario/v1","scenario_id":"learner-upstream-holdover","alarm":{"alarm_id":"synthetic-learner-001","fixture_revision":"learner-v1","data_classification":"synthetic","occurred_at":"2026-09-22T10:00:00Z","domain":"telco-network","severity":"major","required_scopes":["network","openshift_platform","hardware","upstream_timing"],"kpis":{"master_offset_microseconds":140,"lock_state":"holdover"},"diagnostics":{"network":{"status":"ok","observed_at":"2026-09-22T10:01:00Z","provenance":"learner-network-v1","observations":[{"signal":"timing_alarm","state":"present"}]},"openshift_platform":{"status":"ok","observed_at":"2026-09-22T10:01:00Z","provenance":"learner-platform-v1","observations":[{"signal":"platform_timing_fault","state":"absent"}]},"hardware":{"status":"ok","observed_at":"2026-09-22T10:01:00Z","provenance":"learner-hardware-v1","observations":[{"signal":"nic_timestamp_fault","state":"absent"}]},"upstream_timing":{"status":"ok","observed_at":"2026-09-22T10:01:00Z","provenance":"learner-upstream-v1","observations":[{"signal":"upstream_timing_fault","state":"present"}]}}},"knowledge":[{"source_id":"learner-ptp-runbook","source_revision":"v1","excerpt":"Check the upstream grandmaster when local platform and NIC timing diagnostics are healthy during holdover.","tags":["timing_alarm","upstream_timing_fault"]}],"expected_cause":"upstream_timing"}'
qualification="$(jq -cn --argjson scenario "$scenario" '{scenario:$scenario}' | curl "${curl_options[@]}" -X POST "https://${app_host}/api/lab/qualify" -H 'Content-Type: application/json' --data-binary @-)"
jq -e '.overall_result == "pass" and .action_executed == false and (.scenario_results | length) == 5 and all(.scenario_results[]; .passed == true)' <<<"$qualification" >/dev/null

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
runtime_keys="$(oc --kubeconfig "$KUBECONFIG" get secret network-operations-model-runtime -n "$namespace" -o json | jq -c '.data | keys | sort')"
[[ "$runtime_keys" == '["api-key","endpoint","name"]' ]]

stage="evidence"
jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg model "$(jq -r '.model_draft.model' <<<"$investigation")" \
  --arg terminal_scope "$terminal_scope" \
  --arg qualification_id "$(jq -r '.qualification_id' <<<"$qualification")" \
  --argjson runtime_keys "$runtime_keys" \
  '{
    result: "GREEN-live-internal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    readiness: {health: true, mcp_ready: true, workspace_http_status: 200, story_http_status: 200},
    investigation: {cause: "hardware_timing", live_model: true, model: $model, human_approval: true, action_executed: false},
    qualification: {result: "pass", scenarios: 5, qualification_id: $qualification_id},
    terminal_scope: ($terminal_scope | split("\n")),
    runtime_secret_keys: $runtime_keys,
    contains_sensitive_values: false
  }'
