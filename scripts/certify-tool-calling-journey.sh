#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-tool-calling-journey.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-tool-calling-journey.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the execution cluster credential}"

oc() { command oc --kubeconfig "$KUBECONFIG" "$@"; }
actual_cluster="$(oc get namespace "$namespace" -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}')"
[[ "$actual_cluster" == "$expected_cluster" ]]
model="$(oc exec -n "$namespace" deployment/showroom -c terminal -- \
  sh -c 'oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_MODEL}" | base64 -d')"
[[ -n "$model" ]]

request="$(jq -nc --arg model "$model" '{
  model:$model,
  messages:[{role:"user",content:"What is the weather in Austin right now?"}],
  tools:[{
    type:"function",
    function:{
      name:"get_weather",
      description:"Get the current weather for a city",
      parameters:{
        type:"object",
        properties:{city:{type:"string"}},
        required:["city"]
      }
    }
  }],
  tool_choice:"auto",
  max_tokens:128,
  temperature:0
}')"

first_result="$({
  printf '%s' "$request" \
    | oc exec -i -n "$namespace" deploy/showroom -c terminal -- \
        sh -c 'api="$(oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_API_URL}" | base64 -d)"; \
          key="$(oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_API_KEY}" | base64 -d)"; \
          curl -fsS -w "\n%{http_code}\t%{time_total}\n" \
            -H "Authorization: Bearer ${key}" -H "Content-Type: application/json" \
            -X POST "${api%/}/chat/completions" --data-binary @-'
})"
first_response="$(printf '%s\n' "$first_result" | head -1)"
first_metadata="$(printf '%s\n' "$first_result" | tail -1)"

printf '%s' "$first_response" | jq -e '
  .choices[0].message.tool_calls[0].function.name == "get_weather"
  and (
    .choices[0].message.tool_calls[0].function.arguments
    | fromjson
    | .city
    | ascii_downcase
    | contains("austin")
  )
' >/dev/null

assistant_message="$(printf '%s' "$first_response" | jq -c '.choices[0].message')"
final_request="$(jq -nc \
  --arg model "$model" \
  --argjson assistant "$assistant_message" \
  '{
    model:$model,
    messages:[
      {role:"user",content:"What is the weather in Austin right now?"},
      $assistant,
      {
        role:"tool",
        tool_call_id:$assistant.tool_calls[0].id,
        content:"{\"temperature\":78,\"unit\":\"fahrenheit\",\"condition\":\"sunny\"}"
      }
    ],
    max_tokens:128,
    temperature:0
  }')"

final_result="$({
  printf '%s' "$final_request" \
    | oc exec -i -n "$namespace" deploy/showroom -c terminal -- \
        sh -c 'api="$(oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_API_URL}" | base64 -d)"; \
          key="$(oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_API_KEY}" | base64 -d)"; \
          curl -fsS -w "\n%{http_code}\t%{time_total}\n" \
            -H "Authorization: Bearer ${key}" -H "Content-Type: application/json" \
            -X POST "${api%/}/chat/completions" --data-binary @-'
})"
final_response="$(printf '%s\n' "$final_result" | head -1)"
final_metadata="$(printf '%s\n' "$final_result" | tail -1)"

printf '%s' "$final_response" | jq -e '
  .choices[0].message.content as $answer
  | ($answer | type == "string")
    and ($answer | test("78"))
    and ($answer | test("sunny"; "i"))
' >/dev/null

first_seconds="$(printf '%s' "$first_metadata" | cut -f2)"
final_seconds="$(printf '%s' "$final_metadata" | cut -f2)"
total_seconds="$(awk -v first="$first_seconds" -v final="$final_seconds" 'BEGIN {printf "%.6f", first + final}')"
printf '%s\t%s\t200\t%s\tcomplete-tool-protocol=true\n' \
  "$namespace" "$expected_cluster" "$total_seconds"
