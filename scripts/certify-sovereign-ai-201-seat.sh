#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-sovereign-ai-201-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-sovereign-ai-201-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

stage="setup"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
work_dir="$(mktemp -d)"
pf_pid=""
cleanup() {
  [[ -z "$pf_pid" ]] || kill "$pf_pid" >/dev/null 2>&1 || true
  rm -rf "$work_dir"
}
trap cleanup EXIT

request_json() {
  local expected_status="$1" method="$2" url="$3" body="${4:-}"
  local -a args=(-sSk --max-time 30 -o "$work_dir/body" -w '%{http_code}' -X "$method")
  if [[ -n "$body" ]]; then
    args+=(-H 'Content-Type: application/json' --data-binary "$body")
  fi
  local status
  status="$(curl "${args[@]}" "$url")"
  [[ "$status" == "$expected_status" ]]
  jq -e . "$work_dir/body" >/dev/null
  cat "$work_dir/body"
}

stage="route-discovery"
app_host="$(oc --kubeconfig "$KUBECONFIG" get route lab -n "$namespace" -o jsonpath='{.spec.host}')"
[[ -n "$app_host" ]]
base_url="https://${app_host}"

stage="presentation"
presentation_status="$(curl -sSkL --max-time 30 -o /dev/null -w '%{http_code}' "$base_url/")"
[[ "$presentation_status" == "200" ]]

stage="adapter-forward"
oc --kubeconfig "$KUBECONFIG" port-forward -n "$namespace" service/sovereign-ai-201-adapter 18201:8080 >"$work_dir/port-forward.log" 2>&1 &
pf_pid=$!
for _ in {1..30}; do
  curl -fsS --max-time 2 http://127.0.0.1:18201/healthz >"$work_dir/health" && break
  sleep 1
done
api_base="http://127.0.0.1:18201"

stage="health"
health="$(cat "$work_dir/health")"
jq -e '.status == "ok" and .source_state == "REHEARSAL" and .live_identity_complete == true and .authority == "HUMAN_REVIEW_REQUIRED"' <<<"$health" >/dev/null

request_body='{"contract_version":"sovereign-inference/v1","request_id":"8da2153c-16ca-47f9-b0ee-6d8b957add4c","correlation_id":"sovereign-201-cert-001","identity":{"subject":"spiffe://workshop.example/learner","trust_domain":"workshop.example"},"residency":{"data_origin":"local","approved_regions":["local","eu-central"],"destination_region":"local"},"data_classification":"general","requested_model":"granite-3.2-sovereign","prompt":"Explain why deterministic policy must precede model inference.","final_decision_owner":"human-reviewer"}'

stage="allowed-path"
allowed="$(request_json 200 POST "$api_base/api/v1/qualify?condition=allowed" "$request_body")"
jq -e '.outcome == "ALLOWED" and .source_state == "REHEARSAL" and .policy.decision == "ALLOW" and .model_participated == false and .authority == "HUMAN_REVIEW_REQUIRED"' <<<"$allowed" >/dev/null
evidence_id="$(jq -r '.evidence_id' <<<"$allowed")"

stage="evidence"
evidence="$(request_json 200 GET "$api_base/api/v1/evidence/${evidence_id}")"
jq -e '.source_state == "REHEARSAL" and .outcome == "ALLOWED" and .model_participated == false and .secret_values_recorded == false and .authority == "HUMAN_REVIEW_REQUIRED"' <<<"$evidence" >/dev/null

stage="deny-paths"
denied="$(request_json 200 POST "$api_base/api/v1/qualify?condition=denied" "$request_body")"
jq -e '.outcome == "POLICY_DENIED" and .model_participated == false and .policy.decision == "DENY"' <<<"$denied" >/dev/null
injection="$(request_json 200 POST "$api_base/api/v1/qualify?condition=injection" "$request_body")"
jq -e '.outcome == "INJECTION_BLOCKED" and .model_participated == false and .policy.decision == "DENY"' <<<"$injection" >/dev/null

stage="terminal-scope"
terminal_scope="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom -c terminal -- sh -c '
  printf "project=%s\n" "$(oc project -q)"
  printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")"
  if oc get pods -n launchpad-flightpath-candidate >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
  if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
')"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx 'own_edit=yes' <<<"$terminal_scope"
grep -qx 'cross_namespace=DENIED' <<<"$terminal_scope"
grep -qx 'node_list=DENIED' <<<"$terminal_scope"

jq -cn --arg namespace "$namespace" --arg cluster_ref "$expected_cluster" --arg evidence_id "$evidence_id" --arg terminal_scope "$terminal_scope" '{
  result:"GREEN-live-internal-seat", namespace:$namespace, cluster_ref:$cluster_ref,
  readiness:{health:true,presentation_http_status:200},
  journey:{mode:"REHEARSAL",live_qualified:false,model_identity_configured:true,model_participated:false,allow_path:"ALLOWED",deny_path:"POLICY_DENIED",injection_path:"INJECTION_BLOCKED",evidence_id:$evidence_id,evidence_redacted:true,human_authority:true},
  terminal_scope:($terminal_scope|split("\n")), contains_sensitive_values:false
}'
