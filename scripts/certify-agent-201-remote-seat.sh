#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-agent-201-remote-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-agent-201-remote-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

stage="cluster-identity"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest_adapter="$repo_root/scripts/render-agent-201-short-routes.py"

actual_cluster="$(
  oc get namespace "$namespace" \
    -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/cluster-id}'
)"
if [[ "$actual_cluster" != "$expected_cluster" ]]; then
  echo "refusing to mutate cluster '${actual_cluster}'; expected '${expected_cluster}'" >&2
  exit 2
fi

workload_base="${AGENT_201_WORKLOAD_BASE:-}"
if [[ -z "$workload_base" ]]; then
  echo "AGENT_201_WORKLOAD_BASE must identify the exact immutable workload revision" >&2
  exit 4
fi
stage="participant-runtime-contract"
runtime_secret="$(
  oc --kubeconfig "$KUBECONFIG" get secret launchpad-participant-runtime \
    --namespace "$namespace" -o json
)"
endpoint="$(printf '%s' "$runtime_secret" | jq -r '.data.MAAS_ENDPOINT // empty | @base64d')"
model="$(printf '%s' "$runtime_secret" | jq -r '.data.MAAS_MODEL // empty | @base64d')"

if [[ -z "$endpoint" || -z "$model" ]]; then
  echo "participant runtime did not provide the required model connection values" >&2
  exit 3
fi

stage="terminal-readiness"
terminal_ready="false"
for attempt in $(seq 1 30); do
  if oc exec -n "$namespace" deploy/showroom -c terminal -- \
    oc project -q >/dev/null 2>&1; then
    terminal_ready="true"
    break
  fi
  sleep 2
done
if [[ "$terminal_ready" != "true" ]]; then
  printf 'semantic_response=terminal_readiness:false attempts:30\n' >&2
  false
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

for manifest_contract in \
  advisor-prompt-configmap.yaml:none \
  solution-tools.yaml:tools \
  solution-agent.yaml:agent \
  solution-ui.yaml:app
do
  manifest="${manifest_contract%%:*}"
  route_alias="${manifest_contract##*:}"
  stage="workload-apply-${manifest%.yaml}"
  if apply_output="$(
    if [[ "$route_alias" == "none" ]]; then
      curl -fsS "$workload_base/$manifest"
    else
      python3 "$manifest_adapter" --source "$workload_base/$manifest" \
        --route-alias "$route_alias"
    fi \
      | oc exec -i -n "$namespace" deploy/showroom -c terminal -- \
          oc apply -n "$namespace" -f - 2>&1
  )"; then
    :
  else
    failure_class="unknown"
    case "$apply_output" in
      *Forbidden*|*forbidden*) failure_class="forbidden" ;;
      *Invalid*|*invalid*) failure_class="invalid" ;;
      *NotFound*|*"not found"*) failure_class="not-found" ;;
      *Unauthorized*|*unauthorized*) failure_class="unauthorized" ;;
      *AlreadyExists*|*"already exists"*) failure_class="already-exists" ;;
      *Conflict*|*conflict*) failure_class="conflict" ;;
      *timeout*|*Timeout*) failure_class="timeout" ;;
    esac
    failure_reason="$(printf '%s' "$apply_output" | tail -1 | tr '\n\r' '  ' | cut -c1-240)"
    printf 'semantic_response=workload_apply_failure manifest:%s failure_class=%s\n' \
      "${manifest%.yaml}" "$failure_class" >&2
    printf 'semantic_response=workload_apply_reason:%s\n' "$failure_reason" >&2
    false
  fi
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
