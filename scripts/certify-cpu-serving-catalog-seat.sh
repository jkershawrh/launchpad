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
    rag_journey: {
      grounded_answer: ($journey_result | contains("grounded=true"))
    },
    terminal_scope: ($terminal_scope | split("\n")),
    runtime_secret_keys: $runtime_keys,
    contains_sensitive_values: false
  }'
