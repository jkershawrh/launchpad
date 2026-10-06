#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-agent-201-catalog-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-agent-201-catalog-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
showroom_revision="42b250426fd4b5a8c7df843076b9ad8b54bf53a2"
workload_revision="f484cb66c3dcddff323df8814f637dc92c73c179"
workload_base="https://raw.githubusercontent.com/rhpds/triforce/f484cb66c3dcddff323df8814f637dc92c73c179/infrastructure/manifests-201"
expected_tools_image="quay.io/redhat-gpte/triforce-solution-tools@sha256:856874dc984eeb05ec0aeadb6f49265a58687eed17e5a92bc769875d3df44850"
expected_agent_image="ghcr.io/jkershawrh/triforce-solution-agent@sha256:fbe9c2dacb203346e89257aaf097a35bd0e741fe8ddbbc8fea72f4e547961e67"
expected_ui_image="quay.io/redhat-gpte/triforce-solution-ui@sha256:9388d91c19e845b8dcee12ef9037e4b93afadea4df5e7912dbe0a6151b8605fb"
stage="setup"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR

# The remote provisioner intentionally has no cluster-wide pods/exec grant.
# Give this proof runner temporary access only inside the seat namespace, using
# the existing allow-listed edit role, and remove it even when a probe fails.
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
  --namespace "$namespace" \
  --dry-run=client -o yaml \
  | oc --kubeconfig "$KUBECONFIG" apply -f - >/dev/null

setup_result="$(
  AGENT_201_WORKLOAD_BASE="$workload_base" \
    bash "$repo_root/scripts/certify-agent-201-remote-seat.sh" \
    "$namespace" "$expected_cluster"
)"

stage="runtime-images"
tools_image="$(oc --kubeconfig "$KUBECONFIG" get deployment solution-tools -n "$namespace" -o jsonpath='{.spec.template.spec.containers[?(@.name=="solution-tools")].image}')"
agent_image="$(oc --kubeconfig "$KUBECONFIG" get deployment solution-agent -n "$namespace" -o jsonpath='{.spec.template.spec.containers[?(@.name=="solution-agent")].image}')"
ui_image="$(oc --kubeconfig "$KUBECONFIG" get deployment solution-ui -n "$namespace" -o jsonpath='{.spec.template.spec.containers[?(@.name=="solution-ui")].image}')"
[[ "$tools_image" == "$expected_tools_image" ]]
[[ "$agent_image" == "$expected_agent_image" ]]
[[ "$ui_image" == "$expected_ui_image" ]]
for deployment in solution-tools solution-agent solution-ui; do
  expected_var="expected_${deployment#solution-}_image"
  expected_image="${!expected_var}"
  image_id="$(oc --kubeconfig "$KUBECONFIG" get pod -n "$namespace" -l "app=${deployment}" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')"
  [[ "$image_id" == *"${expected_image#*@}" ]]
done

stage="route-discovery"
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
curl_options=(-fsS --retry 3 --retry-all-errors --retry-delay 2 --max-time 180)
stage="tools-health"
[[ "$(curl "${curl_options[@]}" -o /dev/null -w '%{http_code}' "https://${tools_host}/health")" == "200" ]]
stage="agent-health"
[[ "$(curl "${curl_options[@]}" -o /dev/null -w '%{http_code}' "https://${agent_host}/health")" == "200" ]]
stage="app-health"
[[ "$(curl "${curl_options[@]}" -o /dev/null -w '%{http_code}' "https://${app_host}/")" == "200" ]]

stage="tools-contract"
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

stage="model-request"
agent_result="$(
  oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom \
    -c terminal -- \
    curl -fsS --max-time 300 -X POST \
      "http://solution-agent:8082/api/v1/advise" \
      -H 'Content-Type: application/json' \
      --data '{"query":"A retail chain needs real-time inventory prediction across 500 stores on an on-premises OpenShift platform. Recommend a sourced Intel and Red Hat architecture with a migration path."}'
)"
stage="response-contract"
printf '%s' "$agent_result" | jq -e 'type == "object"' >/dev/null
stage="response-inference-errors"
inference_error_count="$(printf '%s' "$agent_result" | jq '[.inference_log[] | select(.error != null)] | length')"
if [[ "$inference_error_count" -ne 0 ]]; then
  inference_http_statuses="$(printf '%s' "$agent_result" | jq -r '[.inference_log[] | .error? // empty | if contains("404") then "404" elif contains("401") then "401" elif contains("403") then "403" elif contains("429") then "429" elif contains("500") then "500" elif contains("502") then "502" elif contains("503") then "503" elif contains("504") then "504" else empty end] | unique | join(",")' 2>/dev/null || true)"
  printf 'semantic_response=inference_error_count:%s inference_http_statuses:%s\n' \
    "$inference_error_count" "${inference_http_statuses:-unknown}" >&2
  false
fi
stage="response-model"
configured_model="$(
  oc --kubeconfig "$KUBECONFIG" get deployment solution-agent -n "$namespace" \
    -o jsonpath='{.spec.template.spec.containers[?(@.name=="solution-agent")].env[?(@.name=="ADVISOR_MODEL")].value}'
)"
[[ "$configured_model" == "granite-3.2-8b-tools" ]]
observed_models="$(
  printf '%s' "$agent_result" \
    | jq -c '[.inference_log[] | select(.model != null) | .model] | unique'
)"
model_count="$(printf '%s' "$observed_models" | jq 'length')"
[[ "$model_count" -ge 1 ]]
printf '%s' "$observed_models" \
  | jq -e --arg configured_model "$configured_model" \
      'all(. == $configured_model)' >/dev/null
stage="response-brief"
brief_type="$(printf '%s' "$agent_result" | jq -r '.brief | type')"
brief_length="$(printf '%s' "$agent_result" | jq -r 'if (.brief | type) == "string" then (.brief | length) else 0 end')"
top_level_keys="$(printf '%s' "$agent_result" | jq -r 'keys | sort | join(",")')"
if [[ "$brief_type" != "string" || "$brief_length" -le 100 ]]; then
  brief_failure_class="$(printf '%s' "$agent_result" | jq -r '.brief // ""' | sed -n 's/^Brief generation failed (\([^,)]*\).*/\1/p')"
  brief_failure_status="$(printf '%s' "$agent_result" | jq -r '.brief // ""' | sed -n 's/^Brief generation failed ([^,]*, status=\([^)]*\)).*/\1/p')"
  printf 'semantic_response=brief_type:%s brief_length:%s failure_class:%s failure_status:%s top_level_keys:%s\n' \
    "$brief_type" "$brief_length" "${brief_failure_class:-none}" \
    "${brief_failure_status:-none}" "$top_level_keys" >&2
  false
fi
stage="response-requirements"
printf '%s' "$agent_result" | jq -e '.requirements != null' >/dev/null
stage="response-hardware-options"
printf '%s' "$agent_result" | jq -e '.hardware_options != null' >/dev/null
stage="response-platform-capabilities"
printf '%s' "$agent_result" | jq -e '.platform_capabilities != null' >/dev/null
stage="response-architecture"
printf '%s' "$agent_result" | jq -e '.architecture != null' >/dev/null
stage="response-hardware-tool"
printf '%s' "$agent_result" | jq -e '[.inference_log[] | select(.tool == "intel_hardware_lookup")] | length >= 1' >/dev/null
stage="response-platform-tool"
printf '%s' "$agent_result" | jq -e '[.inference_log[] | select(.tool == "openshift_capabilities")] | length >= 1' >/dev/null
stage="response-architecture-tool"
printf '%s' "$agent_result" | jq -e '[.inference_log[] | select(.tool == "reference_architectures")] | length >= 1' >/dev/null
tool_count="$(
  printf '%s' "$agent_result" \
    | jq '[.inference_log[] | select(.tool != null) | .tool] | unique | length'
)"
response_sha256="$(printf '%s' "$agent_result" | python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
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
  --arg configured_model "$configured_model" \
  --argjson observed_models "$observed_models" \
  --argjson model_count "$model_count" \
  --arg response_sha256 "$response_sha256" \
  --argjson brief_length "$brief_length" \
  --argjson tool_count "$tool_count" \
  --arg showroom_revision "$showroom_revision" \
  --arg workload_revision "$workload_revision" \
  --arg tools_image "$tools_image" \
  --arg agent_image "$agent_image" \
  --arg ui_image "$ui_image" \
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
    intel_xeon_inference: {
      configured_model: $configured_model,
      observed_models: $observed_models,
      model_participated: ($model_count > 0),
      matches_configured_model: true
    },
    proof_export: {
      response_sha256: $response_sha256,
      brief_length: $brief_length,
      tool_count: $tool_count,
      contains_sensitive_values: false
    },
    provenance: {
      showroom_revision: $showroom_revision,
      workload_revision: $workload_revision
    },
    runtime_images: {
      solution_tools: $tools_image,
      solution_agent: $agent_image,
      solution_ui: $ui_image
    },
    terminal_scope: ($terminal_scope | split("\n")),
    runtime_secret_keys: $runtime_keys,
    contains_sensitive_values: false
  }'
