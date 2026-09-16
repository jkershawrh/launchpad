#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-agent-201-catalog-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-agent-201-catalog-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stage="setup"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR

# The remote provisioner intentionally has no cluster-wide pods/exec grant.
# Give this proof runner temporary access only inside the seat namespace, using
# the existing allow-listed edit role, and remove it even when a probe fails.
probe_binding="launchpad-certification-probe"
cleanup_probe_access() {
  oc --kubeconfig "$KUBECONFIG" delete rolebinding "$probe_binding" \
    --namespace "$namespace" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup_probe_access EXIT
oc --kubeconfig "$KUBECONFIG" create rolebinding "$probe_binding" \
  --clusterrole=edit \
  --serviceaccount=partner-ai-launchpad:launchpad-provisioner \
  --namespace "$namespace" \
  --dry-run=client -o yaml \
  | oc --kubeconfig "$KUBECONFIG" apply -f - >/dev/null

setup_result="$(
  bash "$repo_root/scripts/certify-agent-201-remote-seat.sh" \
    "$namespace" "$expected_cluster"
)"

stage="agent-journey"
tools_host="$(
  oc --kubeconfig "$KUBECONFIG" get route tools -n "$namespace" \
    -o jsonpath='{.spec.host}'
)"
agent_host="$(
  oc --kubeconfig "$KUBECONFIG" get route agent -n "$namespace" \
    -o jsonpath='{.spec.host}'
)"
app_host="$(
  oc --kubeconfig "$KUBECONFIG" get route app -n "$namespace" \
    -o jsonpath='{.spec.host}'
)"
curl_options=(-fsSk --retry 3 --retry-all-errors --retry-delay 2 --max-time 180)
[[ "$(curl "${curl_options[@]}" -o /dev/null -w '%{http_code}' "https://${tools_host}/health")" == "200" ]]
[[ "$(curl "${curl_options[@]}" -o /dev/null -w '%{http_code}' "https://${agent_host}/health")" == "200" ]]
[[ "$(curl "${curl_options[@]}" -o /dev/null -w '%{http_code}' "https://${app_host}/")" == "200" ]]

tools_result="$(
  curl "${curl_options[@]}" -X POST "https://${tools_host}/mcp" \
    -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
)"
printf '%s' "$tools_result" | jq -e '
  [.result.tools[].name] as $names
  | ($names | length) == 3
  and ($names | contains([
    "intel_hardware_lookup",
    "openshift_capabilities",
    "reference_architectures"
  ]))
' >/dev/null

agent_result="$(
  curl "${curl_options[@]}" -X POST "https://${agent_host}/api/v1/advise" \
    -H 'Content-Type: application/json' \
    --data '{"query":"A retail chain needs real-time inventory prediction across 500 stores on an on-premises OpenShift platform. Recommend a sourced Intel and Red Hat architecture with a migration path."}'
)"
printf '%s' "$agent_result" | jq -e '
  (.brief | type == "string" and length > 100)
  and (.requirements != null)
  and (.hardware_options != null)
  and (.platform_capabilities != null)
  and (.architecture != null)
  and ([.inference_log[] | select(.error != null)] | length == 0)
  and ([.inference_log[] | select(.tool == "intel_hardware_lookup")] | length >= 1)
  and ([.inference_log[] | select(.tool == "openshift_capabilities")] | length >= 1)
  and ([.inference_log[] | select(.tool == "reference_architectures")] | length >= 1)
' >/dev/null
journey_result="functional-agent=true"

stage="terminal-scope"
terminal_scope="$(
  oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom \
    -c terminal -- sh -c '
      printf "project=%s\n" "$(oc project -q)"
      printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")"
      if oc get pods -n partner-ai-launchpad >/dev/null 2>&1; then
        echo cross_namespace=ALLOWED
      else
        echo cross_namespace=DENIED
      fi
      if oc get nodes >/dev/null 2>&1; then
        echo node_list=ALLOWED
      else
        echo node_list=DENIED
      fi
    '
)"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx 'own_edit=yes' <<<"$terminal_scope"
grep -qx 'cross_namespace=DENIED' <<<"$terminal_scope"
grep -qx 'node_list=DENIED' <<<"$terminal_scope"

stage="runtime-contract"
runtime_keys="$(
  oc --kubeconfig "$KUBECONFIG" get secret launchpad-participant-runtime \
    -n "$namespace" -o json | jq -c '.data | keys | sort'
)"
[[ "$runtime_keys" == '["MAAS_API_KEY","MAAS_API_URL","MAAS_ENDPOINT","MAAS_MODEL"]' ]]

stage="evidence"
jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg setup_result "$setup_result" \
  --arg journey_result "$journey_result" \
  --arg terminal_scope "$terminal_scope" \
  --argjson runtime_keys "$runtime_keys" \
  '{
    result: "GREEN-live-internal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    setup_passed: ($setup_result | contains("deployed")),
    agent_journey: {
      functional_agent: ($journey_result | contains("functional-agent=true"))
    },
    terminal_scope: ($terminal_scope | split("\n")),
    runtime_secret_keys: $runtime_keys,
    contains_sensitive_values: false
  }'
