#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-agent-201-remote-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-agent-201-remote-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

stage="cluster-identity"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR

actual_cluster="$(
  oc get namespace "$namespace" \
    -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}'
)"
if [[ "$actual_cluster" != "$expected_cluster" ]]; then
  echo "refusing to mutate cluster '${actual_cluster}'; expected '${expected_cluster}'" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stage="showroom-contract"
host="$(oc get route showroom -n "$namespace" -o jsonpath='{.spec.host}')"
curl_options=(-fsSk)
if [[ -n "${LAUNCHPAD_CURL_INTERFACE:-}" ]]; then
  curl_options+=(--interface "$LAUNCHPAD_CURL_INTERFACE")
fi
if [[ -n "${LAUNCHPAD_INGRESS_IP:-}" ]]; then
  curl_options+=(--resolve "${host}:443:${LAUNCHPAD_INGRESS_IP}")
fi
page="$(curl "${curl_options[@]}" "https://${host}/www/modules/02-deploy-tools.html")"
endpoint="$(printf '%s' "$page" | sed -n "s/.*--from-literal=api-base='\([^']*\)'.*/\1/p" | head -1)"
model="$(printf '%s' "$page" | sed -n "s/.*ADVISOR_MODEL='\([^']*\)'.*/\1/p" | head -1)"

if [[ -z "$endpoint" || -z "$model" ]]; then
  echo "Showroom did not render the required model connection values" >&2
  exit 3
fi

stage="connection-config"
oc create configmap racmaas-connection \
  --from-literal="api-base=${endpoint}" \
  --dry-run=client -o yaml \
  | oc exec -i -n "$namespace" deploy/showroom -c terminal -- \
      oc apply -n "$namespace" -f - >/dev/null

# Copy the already-issued key between namespace Secrets as base64 data. An
# `oc exec` process does not inherit values exported dynamically by the
# terminal entrypoint, so reading `$MAAS_API_KEY` there can silently create an
# empty Secret. This pipeline never decodes or prints the credential locally.
stage="model-key-binding"
oc --kubeconfig "$KUBECONFIG" get secret launchpad-participant-runtime \
  --namespace "$namespace" -o json \
  | jq --arg namespace "$namespace" '{
      apiVersion: "v1",
      kind: "Secret",
      metadata: {name: "litellm-api-key", namespace: $namespace},
      type: "Opaque",
      data: {"api-key": .data.MAAS_API_KEY}
    }' \
  | oc --kubeconfig "$KUBECONFIG" apply -f - >/dev/null
test -n "$(
  oc --kubeconfig "$KUBECONFIG" get secret litellm-api-key \
    --namespace "$namespace" -o jsonpath='{.data.api-key}'
)"

stage="workload-apply"
for manifest in \
  advisor-prompt-configmap.yaml \
  solution-tools.yaml \
  solution-agent.yaml \
  solution-ui.yaml
do
  oc exec -i -n "$namespace" deploy/showroom -c terminal -- \
    oc apply -n "$namespace" -f - \
    < "$repo_root/content-intel-xeon6-agent-201/manifests/$manifest" >/dev/null
done

stage="workload-model-config"
oc exec -n "$namespace" deploy/showroom -c terminal -- \
  oc set env -n "$namespace" deployment/solution-agent \
  --containers=solution-agent \
  "ADVISOR_MODEL=${model}" >/dev/null

stage="workload-readiness"
for deployment in solution-agent solution-ui; do
  oc exec -n "$namespace" deploy/showroom -c terminal -- \
    oc rollout status -n "$namespace" "deployment/${deployment}" \
      --timeout=300s >/dev/null
done

printf '%s\t%s\tdeployed\n' "$namespace" "$expected_cluster"
