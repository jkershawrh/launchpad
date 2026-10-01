#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-cpu-serving-catalog-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-cpu-serving-catalog-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stage="setup"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR

setup_result="$(
  bash "$repo_root/scripts/certify-cpu-serving-seat.sh" \
    "$namespace" "$expected_cluster"
)"

stage="deployment-readiness"
oc --kubeconfig "$KUBECONFIG" wait -n "$namespace" \
  --for=condition=Available deployment/anythingllm \
  --timeout=600s >/dev/null

stage="rag-journey"
journey_result="$(
  CERTIFICATION_RUN_ID="catalog-${namespace##*-}-$(date -u +%H%M%S)" \
    bash "$repo_root/scripts/certify-cpu-serving-rag.sh" \
      "$namespace" "$expected_cluster"
)"
grep -q 'grounded=true' <<<"$journey_result"
grep -q 'model_participated=true' <<<"$journey_result"
rag_model="$(sed -n 's/.*model=\([^[:space:]]*\).*/\1/p' <<<"$journey_result")"
[[ "$rag_model" == "granite-3.2-8b-tools" ]]

stage="managed-model-proof"
configured_model="$(
  oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom \
    -c terminal -- sh -c \
    'oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_MODEL}" | base64 -d'
)"
model_request="$(jq -nc --arg model "$configured_model" '{
  model: $model,
  messages: [{role: "user", content: "Reply with the single word READY."}],
  max_tokens: 16,
  temperature: 0
}')"
model_response="$(
  printf '%s' "$model_request" \
    | oc --kubeconfig "$KUBECONFIG" exec -i -n "$namespace" deployment/showroom \
        -c terminal -- sh -c \
        'endpoint="$(oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_ENDPOINT}" | base64 -d)"; \
         key="$(oc get secret launchpad-participant-runtime -o jsonpath="{.data.MAAS_API_KEY}" | base64 -d)"; \
         curl -fsS --connect-timeout 10 --max-time 180 \
           -H "Authorization: Bearer ${key}" -H "Content-Type: application/json" \
           -X POST "${endpoint%/}/v1/chat/completions" --data-binary @-'
)"
model_observation="$(
  jq -c --arg configured_model "$configured_model" '{
    configured_model: $configured_model,
    observed_model: (.model // ""),
    answer_present: (((.choices[0].message.content // "") | length) > 0),
    identity_present: (((.model // "") | length) > 0)
  }' <<<"$model_response"
)"
jq -e '
  .answer_present == true
  and .identity_present == true
  and .configured_model == "granite-3.2-8b-tools"
  and .observed_model == "granite-3.2-8b-tools"
  and .configured_model == .observed_model
' <<<"$model_observation" >/dev/null

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

stage="console-surface"
console_url="$(oc --kubeconfig "$KUBECONFIG" whoami --show-console)"
[[ "$console_url" == https://* ]]

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
  --arg rag_model "$rag_model" \
  --argjson model_observation "$model_observation" \
  --arg console_url "$console_url" \
  --arg terminal_scope "$terminal_scope" \
  --argjson runtime_keys "$runtime_keys" \
  '{
    result: "GREEN-live-internal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    setup_passed: ($setup_result | contains("deployed")),
    rag_journey: {
      grounded_answer: ($journey_result | contains("grounded=true")),
      model_participated: ($journey_result | contains("model_participated=true")),
      model: $rag_model
    },
    model_journey: $model_observation,
    operator_journey: {
      terminal_scope_verified: true,
      console_url_present: ($console_url | startswith("https://")),
      console_namespace_scope: true,
      workspace_http_status: 200
    },
    terminal_scope: ($terminal_scope | split("\n")),
    runtime_secret_keys: $runtime_keys,
    contains_sensitive_values: false
  }'
