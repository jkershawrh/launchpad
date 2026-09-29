#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-tool-calling-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-tool-calling-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the execution cluster credential}"

stage=cluster-identity
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR

oc() { command oc --kubeconfig "$KUBECONFIG" "$@"; }

actual_cluster="$(oc get namespace "$namespace" -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}')"
[[ "$actual_cluster" == "$expected_cluster" ]]

stage=showroom-readiness
oc wait -n "$namespace" --for=condition=Ready pod \
  -l app.kubernetes.io/name=showroom --timeout=300s >/dev/null

stage=runtime-contract
runtime_json="$(oc exec -n "$namespace" deployment/showroom -c terminal -- \
  oc get secret launchpad-participant-runtime -n "$namespace" -o json)"
runtime_keys="$(jq -c '.data | keys | sort' <<<"$runtime_json")"
jq -e '(.data.MAAS_API_KEY | length > 0) and (.data.MAAS_MODEL | length > 0)' \
  <<<"$runtime_json" >/dev/null
model_url="$(jq -r '(.data.MAAS_API_URL // .data.MAAS_ENDPOINT) | @base64d' <<<"$runtime_json")"
model_url="${model_url%/}"
[[ "$model_url" == */v1 ]] || model_url="${model_url}/v1"
model_name="$(jq -r '.data.MAAS_MODEL | @base64d' <<<"$runtime_json")"
model_key="$(jq -r '.data.MAAS_API_KEY | @base64d' <<<"$runtime_json")"

stage=model-list
models_response="$(oc exec -n "$namespace" deployment/showroom -c terminal -- \
  curl -kfsS -w $'\n%{http_code}' -H "Authorization: Bearer ${model_key}" \
    "${model_url}/models")"
models_status="${models_response##*$'\n'}"
[[ "$models_status" == 200 ]]

stage=structured-tool-call
request="$(jq -nc --arg model "$model_name" '{
  model:$model,
  messages:[{role:"user",content:"What is the weather in Austin right now?"}],
  tools:[{type:"function",function:{name:"get_weather",description:"Get current weather",parameters:{type:"object",properties:{city:{type:"string"}},required:["city"]}}}],
  tool_choice:"auto",max_tokens:128,temperature:0
}')"
first="$(printf '%s' "$request" | oc exec -i -n "$namespace" deployment/showroom -c terminal -- \
  curl -kfsS -H "Authorization: Bearer ${model_key}" -H 'Content-Type: application/json' \
    -X POST "${model_url}/chat/completions" --data-binary @-)"
tool_call="$(jq -c '.choices[0].message.tool_calls[0]' <<<"$first")"
jq -e '.function.name == "get_weather" and (.function.arguments | fromjson | .city | ascii_downcase | contains("austin"))' \
  <<<"$tool_call" >/dev/null

stage=complete-tool-protocol
assistant="$(jq -c '.choices[0].message' <<<"$first")"
final_request="$(jq -nc --arg model "$model_name" --argjson assistant "$assistant" '{
  model:$model,
  messages:[
    {role:"user",content:"What is the weather in Austin right now?"},
    $assistant,
    {role:"tool",tool_call_id:$assistant.tool_calls[0].id,content:"{\"temperature\":78,\"unit\":\"fahrenheit\",\"condition\":\"sunny\"}"}
  ],max_tokens:128,temperature:0
}')"
final="$(printf '%s' "$final_request" | oc exec -i -n "$namespace" deployment/showroom -c terminal -- \
  curl -kfsS -H "Authorization: Bearer ${model_key}" -H 'Content-Type: application/json' \
    -X POST "${model_url}/chat/completions" --data-binary @-)"
jq -e '.choices[0].message.content | type == "string" and test("78") and test("sunny"; "i")' \
  <<<"$final" >/dev/null

stage=terminal-scope
terminal_scope="$(oc exec -n "$namespace" deployment/showroom -c terminal -- sh -c '
  printf "project=%s\n" "$(oc project -q)"
  printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")"
  if oc get pods -n partner-ai-launchpad >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
  if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
')"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx own_edit=yes <<<"$terminal_scope"
grep -qx cross_namespace=DENIED <<<"$terminal_scope"
grep -qx node_list=DENIED <<<"$terminal_scope"

jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --argjson runtime_keys "$runtime_keys" \
  --argjson models_status "$models_status" \
  --arg terminal_scope "$terminal_scope" \
  '{
    result:"GREEN-live-internal-seat",
    namespace:$namespace,
    cluster_ref:$cluster_ref,
    runtime_secret_keys:$runtime_keys,
    model:{models_http_status:$models_status,structured_tool_call:true,complete_tool_protocol:true},
    terminal_scope:($terminal_scope | split("\n")),
    contains_sensitive_values:false
  }'
