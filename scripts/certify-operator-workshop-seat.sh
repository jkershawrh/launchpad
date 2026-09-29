#!/usr/bin/env bash
set -euo pipefail
namespace="${1:?usage: certify-operator-workshop-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-operator-workshop-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the execution cluster credential}"
stage=cluster-identity
cleanup_exercise=false
oc() { command oc --kubeconfig "$KUBECONFIG" "$@"; }
cleanup() {
  if [[ "$cleanup_exercise" == true ]]; then
    oc delete route,service,deployment launchpad-cert-hello -n "$namespace" --ignore-not-found >/dev/null 2>&1 || true
  fi
}
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
trap cleanup EXIT

actual_cluster="$(oc get namespace "$namespace" -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}')"
[[ "$actual_cluster" == "$expected_cluster" ]]

stage=showroom-readiness
oc wait -n "$namespace" --for=condition=Ready pod -l app.kubernetes.io/name=showroom --timeout=300s >/dev/null

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

stage=learner-exercise
cleanup_exercise=true
oc create deployment launchpad-cert-hello --image=quay.io/openshifttest/hello-openshift:1.2.0 -n "$namespace" >/dev/null
oc expose deployment launchpad-cert-hello --port=8080 -n "$namespace" >/dev/null
ingress_domain="$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}')"
seat_suffix="${namespace##*-}"
route_host="cert-${seat_suffix}.${ingress_domain}"
oc expose service launchpad-cert-hello --hostname="$route_host" -n "$namespace" >/dev/null
oc rollout status deployment/launchpad-cert-hello -n "$namespace" --timeout=180s >/dev/null
[[ "$(oc get route launchpad-cert-hello -n "$namespace" -o jsonpath='{.spec.host}')" == "$route_host" ]]
route_status=000
response=''
for _ in {1..30}; do
  response="$(curl -fsS "http://${route_host}" 2>/dev/null || true)"
  route_status="$(curl -sS -o /dev/null -w '%{http_code}' "http://${route_host}" 2>/dev/null || true)"
  [[ "$route_status" == 200 ]] && break
  sleep 2
done
[[ "$route_status" == 200 ]]
grep -Fq 'Hello OpenShift!' <<<"$response"

stage=exercise-cleanup
oc delete route,service,deployment launchpad-cert-hello -n "$namespace" --ignore-not-found >/dev/null
cleanup_exercise=false
remaining="$(oc get deployment,service,route launchpad-cert-hello -n "$namespace" --ignore-not-found -o name)"
[[ -z "$remaining" ]]

jq -cn --arg namespace "$namespace" --arg cluster_ref "$expected_cluster" \
  --arg terminal_scope "$terminal_scope" --argjson route_status "$route_status" '{
    result:"GREEN-live-internal-seat",namespace:$namespace,cluster_ref:$cluster_ref,
    exercise:{rollout_ready:true,route_http_status:$route_status,response_marker:true,resources_removed:true},
    terminal_scope:($terminal_scope | split("\n")),contains_sensitive_values:false
  }'
