#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-operator-workshop-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-operator-workshop-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the execution cluster credential}"

task_name=launchpad-cert-operator-evidence
pipeline_name=launchpad-cert-operator-evidence
run_name=launchpad-cert-operator-evidence-run
stage=cluster-identity
cleanup_exercise=false

oc() { command oc --kubeconfig "$KUBECONFIG" "$@"; }

cleanup() {
  if [[ "$cleanup_exercise" == true ]]; then
    oc delete pipelinerun "$run_name" -n "$namespace" \
      --ignore-not-found --wait=false >/dev/null 2>&1 || true
    oc delete pipeline "$pipeline_name" task "$task_name" -n "$namespace" \
      --ignore-not-found --wait=false >/dev/null 2>&1 || true
  fi
}

trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
trap cleanup EXIT

actual_cluster="$(oc get namespace "$namespace" -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}')"
[[ "$actual_cluster" == "$expected_cluster" ]]

stage=showroom-readiness
oc wait -n "$namespace" --for=condition=Ready pod \
  -l app.kubernetes.io/name=showroom --timeout=300s >/dev/null

stage=terminal-scope
terminal_scope="$(oc exec -n "$namespace" deployment/showroom -c terminal -- sh -c '
  printf "project=%s\n" "$(oc project -q)"
  printf "own_edit=%s\n" "$(oc auth can-i create tasks.tekton.dev -n "$PROJECT_NAME")"
  printf "pipeline_create=%s\n" "$(oc auth can-i create pipelines.tekton.dev -n "$PROJECT_NAME")"
  printf "run_create=%s\n" "$(oc auth can-i create pipelineruns.tekton.dev -n "$PROJECT_NAME")"
  if oc get pods -n partner-ai-launchpad >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
  if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
')"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx own_edit=yes <<<"$terminal_scope"
grep -qx pipeline_create=yes <<<"$terminal_scope"
grep -qx run_create=yes <<<"$terminal_scope"
grep -qx cross_namespace=DENIED <<<"$terminal_scope"
grep -qx node_list=DENIED <<<"$terminal_scope"

stage=operator-capability
for resource in tasks pipelines pipelineruns taskruns; do
  oc get --raw "/apis/tekton.dev/v1" \
    | jq -e --arg resource "$resource" \
      '.resources | any(.name == $resource and .namespaced == true)' >/dev/null
done
tekton_version="$(oc get tektonconfig.operator.tekton.dev config \
  -o jsonpath='{.status.version}')"
[[ -n "$tekton_version" ]]

stage=operator-reconciliation
cleanup_exercise=true
oc apply -n "$namespace" -f - >/dev/null <<EOF
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: ${task_name}
  labels:
    launchpad.redhat.com/certification-exercise: operator-pipeline
spec:
  params:
    - name: scenario
      type: string
  results:
    - name: evidence
      description: Reconciliation evidence emitted by the certification Task
  steps:
    - name: produce-evidence
      image: registry.access.redhat.com/ubi9/ubi-minimal@sha256:d1bad2a2790eac1651e57e78159a81b72ddfa7b836936b26cf51e09744bf1c2d
      script: |
        #!/bin/sh
        set -eu
        message="operator-reconciled:\$(params.scenario)"
        printf '%s\n' "\$message"
        printf '%s' "\$message" > "\$(results.evidence.path)"
---
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: ${pipeline_name}
  labels:
    launchpad.redhat.com/certification-exercise: operator-pipeline
spec:
  params:
    - name: scenario
      type: string
  tasks:
    - name: collect-evidence
      taskRef:
        name: ${task_name}
      params:
        - name: scenario
          value: \$(params.scenario)
  results:
    - name: evidence
      value: \$(tasks.collect-evidence.results.evidence)
---
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${run_name}
  labels:
    launchpad.redhat.com/certification-exercise: operator-pipeline
spec:
  pipelineRef:
    name: ${pipeline_name}
  params:
    - name: scenario
      value: certify-namespace-reconciliation
EOF

oc wait pipelinerun/"$run_name" -n "$namespace" \
  --for=condition=Succeeded --timeout=300s >/dev/null
run_status="$(oc get pipelinerun "$run_name" -n "$namespace" \
  -o jsonpath='{.status.conditions[?(@.type=="Succeeded")].status}')"
[[ "$run_status" == True ]]
result="$(oc get pipelinerun "$run_name" -n "$namespace" \
  -o jsonpath='{.status.results[?(@.name=="evidence")].value}')"
[[ "$result" == operator-reconciled:certify-namespace-reconciliation ]]
taskrun_count="$(oc get taskrun -n "$namespace" \
  -l "tekton.dev/pipelineRun=${run_name}" -o json | jq '.items | length')"
[[ "$taskrun_count" -eq 1 ]]

stage=exercise-cleanup
oc delete pipelinerun "$run_name" -n "$namespace" \
  --ignore-not-found --wait=true >/dev/null
oc delete pipeline "$pipeline_name" task "$task_name" -n "$namespace" \
  --ignore-not-found --wait=true >/dev/null

remaining=unknown
for _ in {1..30}; do
  remaining="$({
    oc get task "$task_name" pipeline "$pipeline_name" pipelinerun "$run_name" \
      -n "$namespace" --ignore-not-found -o name
    oc get taskrun,pod -n "$namespace" \
      -l "tekton.dev/pipelineRun=${run_name}" --ignore-not-found -o name
  } | sed '/^$/d')"
  [[ -z "$remaining" ]] && break
  sleep 2
done
[[ -z "$remaining" ]]
cleanup_exercise=false

jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg terminal_scope "$terminal_scope" \
  --arg tekton_version "$tekton_version" \
  --arg result_value "$result" \
  --argjson taskrun_count "$taskrun_count" \
  '{
    result:"GREEN-live-internal-seat",
    namespace:$namespace,
    cluster_ref:$cluster_ref,
    operator:{
      api_available:true,
      version:$tekton_version,
      run_succeeded:true,
      result_marker:($result_value == "operator-reconciled:certify-namespace-reconciliation"),
      taskrun_count:$taskrun_count,
      resources_removed:true
    },
    terminal_scope:($terminal_scope | split("\n")),
    contains_sensitive_values:false
  }'
