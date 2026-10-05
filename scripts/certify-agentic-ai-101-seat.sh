#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-agentic-ai-101-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-agentic-ai-101-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

source_revision="f79869c962c37456373d2a8061d2e4274c2c12b5"
expected_presentation_image="ghcr.io/jkershawrh/agentic-ai-101-presentation@sha256:bc9d4db4534e08551ff48938f6e840a27fe1373045586e922d3b100afae2edf9"
expected_rehearsal_image="ghcr.io/jkershawrh/agentic-ai-101-rehearsal@sha256:1fedfffd99183023350cbff16c9535fb3ff9bb67a3ca44f575d6a50d8cfc5a6a"

stage="setup"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR

stage="workload-readiness"
oc --kubeconfig "$KUBECONFIG" rollout status deployment/agentic-ai-101 \
  -n "$namespace" --timeout=300s >/dev/null
oc --kubeconfig "$KUBECONFIG" rollout status deployment/agentic-ai-101-presentation \
  -n "$namespace" --timeout=300s >/dev/null

stage="runtime-images"
presentation_image="$(oc --kubeconfig "$KUBECONFIG" get deployment agentic-ai-101-presentation -n "$namespace" -o jsonpath='{.spec.template.spec.containers[0].image}')"
rehearsal_image="$(oc --kubeconfig "$KUBECONFIG" get deployment agentic-ai-101 -n "$namespace" -o jsonpath='{.spec.template.spec.containers[0].image}')"
[[ "$presentation_image" == "$expected_presentation_image" ]]
[[ "$rehearsal_image" == "$expected_rehearsal_image" ]]
presentation_image_id="$(oc --kubeconfig "$KUBECONFIG" get pod -n "$namespace" -l app.kubernetes.io/component=presentation -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')"
rehearsal_image_id="$(oc --kubeconfig "$KUBECONFIG" get pod -n "$namespace" -l app.kubernetes.io/component=rehearsal-service -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')"
[[ "$presentation_image_id" == *"${expected_presentation_image#*@}" ]]
[[ "$rehearsal_image_id" == *"${expected_rehearsal_image#*@}" ]]

stage="presentation"
presentation_host="$(oc --kubeconfig "$KUBECONFIG" get route story -n "$namespace" -o jsonpath='{.spec.host}')"
presentation="$(curl -fksS --retry 4 --retry-all-errors --retry-delay 2 --max-time 180 "https://${presentation_host}/")"
grep -q 'Agentic AI 101' <<<"$presentation"

runtime_pod="$(oc --kubeconfig "$KUBECONFIG" get pod -n "$namespace" -l app.kubernetes.io/component=rehearsal-service -o jsonpath='{.items[0].metadata.name}')"
runtime_request() {
  local scenario="$1"
  oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" "$runtime_pod" -- \
    node -e "fetch('http://127.0.0.1:8080/api/v1/workflows/run',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({scenario:'${scenario}'})}).then(async response=>{process.stdout.write(JSON.stringify({status:response.status,body:await response.json()}))})"
}

stage="rehearsal-health"
health="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" "$runtime_pod" -- node -e "fetch('http://127.0.0.1:8080/healthz').then(response=>response.text()).then(text=>process.stdout.write(text))")"
ready="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" "$runtime_pod" -- node -e "fetch('http://127.0.0.1:8080/readyz').then(response=>response.text()).then(text=>process.stdout.write(text))")"
jq -e '.status == "ok" and .sourceState == "REHEARSAL"' <<<"$health" >/dev/null
jq -e '.status == "ok" and .sourceState == "REHEARSAL"' <<<"$ready" >/dev/null

stage="workflow"
read_only_first="$(runtime_request read-only)"
read_only_second="$(runtime_request read-only)"
state_change="$(runtime_request state-change)"
unknown="$(runtime_request unknown)"
jq -e '.status == 200 and .body.policyDecision == "explanation permitted" and .body.targetMutated == false' <<<"$read_only_first" >/dev/null
test "$read_only_first" = "$read_only_second"
jq -e '.status == 200 and .body.policyDecision == "deny and escalate" and .body.targetMutated == false and (.body.humanAuthority | contains("approval required"))' <<<"$state_change" >/dev/null
jq -e '.status == 400 and .body.error == "unsupported_scenario"' <<<"$unknown" >/dev/null

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

stage="evidence"
jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg presentation_host "$presentation_host" \
  --arg terminal_scope "$terminal_scope" \
  --arg source_revision "$source_revision" \
  --arg presentation_image "$presentation_image" \
  --arg rehearsal_image "$rehearsal_image" \
  '{
    result: "GREEN-destination-rehearsal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    source_state: "REHEARSAL",
    inference: {required: false, participated: false},
    provenance: {source_revision: $source_revision},
    runtime_images: {presentation: $presentation_image, rehearsal: $rehearsal_image},
    readiness: {presentation: true, rehearsal: true},
    presentation_host: $presentation_host,
    workflow: {
      read_only_grounded: true,
      deterministic_replay: true,
      state_change_denied: true,
      target_mutated: false,
      unknown_scenario_rejected: true
    },
    authority: {human_review_required: true},
    terminal_scope: ($terminal_scope | split("\n")),
    contains_sensitive_values: false
  }'
