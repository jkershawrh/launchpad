#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-cpu-serving-rag.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-cpu-serving-rag.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

oc() {
  command oc --kubeconfig "$KUBECONFIG" "$@"
}

actual_cluster="$(
  oc get namespace "$namespace" \
    -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}'
)"
if [[ "$actual_cluster" != "$expected_cluster" ]]; then
  echo "refusing to validate cluster '${actual_cluster}'; expected '${expected_cluster}'" >&2
  exit 2
fi

host="$(oc get route rag -n "$namespace" -o jsonpath='{.spec.host}')"
base_url="https://${host}"
route_ready_attempts="${LAUNCHPAD_ROUTE_READY_ATTEMPTS:-40}"
if ! [[ "$route_ready_attempts" =~ ^[1-9][0-9]*$ ]]; then
  echo "LAUNCHPAD_ROUTE_READY_ATTEMPTS must be a positive integer" >&2
  exit 64
fi

wait_for_route() {
  local attempt http_status
  for ((attempt = 1; attempt <= route_ready_attempts; attempt++)); do
    http_status="$(
      curl -sSk -o /dev/null -w '%{http_code}' \
        --connect-timeout 3 --max-time 5 \
        "${base_url}/api/ping" 2>/dev/null || true
    )"
    if [[ "$http_status" == "200" ]]; then
      return 0
    fi
    sleep 3
  done
  echo "AnythingLLM Route did not become ready after ${route_ready_attempts} attempts" >&2
  return 1
}

wait_for_route
run_id="${CERTIFICATION_RUN_ID:-$(date -u +%Y%m%d%H%M%S)-$$}"
run_id="$(printf '%s' "$run_id" | tr -cd '[:alnum:]-' | tr '[:upper:]' '[:lower:]')"
workspace_slug="hr-assistant-${run_id}"
curl_options=(
  -fsSk
  --retry 3
  --retry-all-errors
  --retry-delay 2
  --connect-timeout 10
  --max-time 180
)
if [[ -n "${LAUNCHPAD_CURL_INTERFACE:-}" ]]; then
  curl_options+=(--interface "$LAUNCHPAD_CURL_INTERFACE")
fi
if [[ -n "${LAUNCHPAD_INGRESS_IP:-}" ]]; then
  curl_options+=(--resolve "${host}:443:${LAUNCHPAD_INGRESS_IP}")
fi
api_token="$({
  curl "${curl_options[@]}" \
    -H 'Content-Type: application/json' \
    -X POST "${base_url}/api/system/generate-api-key" \
    --data '{"name":"launchpad-rag-certification"}'
} | jq -r '.apiKey.secret')"

if [[ -z "$api_token" || "$api_token" == "null" ]]; then
  echo "AnythingLLM did not issue a certification API token" >&2
  exit 3
fi

auth_ok="$(curl "${curl_options[@]}" -H "Authorization: Bearer ${api_token}" \
  "${base_url}/api/v1/auth" | jq -r '.authenticated')"
[[ "$auth_ok" == "true" ]]

curl "${curl_options[@]}" \
  -H "Authorization: Bearer ${api_token}" \
  -H 'Content-Type: application/json' \
  -X POST "${base_url}/api/v1/workspace/new" \
  --data "$(jq -nc --arg name "$workspace_slug" '{name:$name,chatMode:"query",openAiTemp:0,openAiHistory:10,topN:4}')" \
  | jq -e --arg slug "$workspace_slug" '.workspace.slug == $slug' >/dev/null

curl "${curl_options[@]}" \
  -H "Authorization: Bearer ${api_token}" \
  -H 'Content-Type: application/json' \
  -X POST "${base_url}/api/v1/document/raw-text" \
  --data "$(jq -nc --arg workspace "$workspace_slug" '{textContent:"Launchpad Orion Leave Policy. Every employee receives exactly 17 days of Orion leave per calendar year. This policy fact is unique to this certification document.",addToWorkspaces:$workspace,metadata:{title:"orion-leave-policy.txt",docSource:"launchpad-certification"}}')" \
  | jq -e '.success == true and .documents[0].title == "orion-leave-policy.txt"' \
  >/dev/null

result="$(curl "${curl_options[@]}" \
  -w $'\n%{http_code}\t%{time_total}\n' \
  -H "Authorization: Bearer ${api_token}" \
  -H 'Content-Type: application/json' \
  -X POST "${base_url}/api/v1/workspace/${workspace_slug}/chat" \
  --data '{"message":"According to the supplied policy, exactly how many days of Orion leave does every employee receive per calendar year?","mode":"query"}')"
response="$(printf '%s\n' "$result" | head -1)"
metadata="$(printf '%s\n' "$result" | tail -1)"

printf '%s' "$response" | jq -e '
  .type == "textResponse"
  and (.textResponse | contains("17"))
  and any(.sources[]?; .title == "orion-leave-policy.txt")
  and (.error == null)
' >/dev/null

printf '%s\t%s\t%s\tgrounded=true\n' \
  "$namespace" "$expected_cluster" "$metadata"
