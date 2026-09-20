#!/usr/bin/env bash
set -euo pipefail

namespace="launchpad-stage"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
overlay="$repo_root/deploy/launchpad/overlays/flightpath-stage"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ $# -eq 1 ]] || fail "usage: $0 /explicit/flightpath.kubeconfig"
kubeconfig="$1"
[[ -f "$kubeconfig" ]] || fail "Flightpath kubeconfig is not a file"

server="$(KUBECONFIG="$kubeconfig" oc whoami --show-server)"
[[ "$server" == *"api.flightpath.fm2aihpcsed.com"* ]] \
  || fail "kubeconfig is not Flightpath: $server"

KUBECONFIG="$kubeconfig" oc apply -f "$overlay/namespace.yaml"

if ! KUBECONFIG="$kubeconfig" oc -n "$namespace" get secret \
  launchpad-registry-pull >/dev/null 2>&1; then
  KUBECONFIG="$kubeconfig" oc -n partner-ai-launchpad get secret \
    launchpad-registry-pull -o json \
    | jq 'del(.metadata.annotations, .metadata.creationTimestamp,
        .metadata.managedFields, .metadata.ownerReferences,
        .metadata.resourceVersion, .metadata.uid)
        | .metadata.namespace = "launchpad-stage"' \
    | KUBECONFIG="$kubeconfig" oc apply -f -
fi

if ! KUBECONFIG="$kubeconfig" oc -n "$namespace" get secret \
  launchpad-db-secret >/dev/null 2>&1; then
  password="$(openssl rand -hex 32)"
  database_url="postgresql://launchpad_stage:${password}@postgres:5432/launchpad_stage"
  KUBECONFIG="$kubeconfig" oc -n "$namespace" create secret generic \
    launchpad-db-secret \
    --from-literal=POSTGRES_DB=launchpad_stage \
    --from-literal=POSTGRES_USER=launchpad_stage \
    --from-literal=POSTGRES_PASSWORD="$password" \
    --from-literal=DATABASE_URL="$database_url"
  unset password database_url
fi

KUBECONFIG="$kubeconfig" oc apply -k "$overlay"
KUBECONFIG="$kubeconfig" oc -n "$namespace" rollout status \
  deployment/postgres --timeout=5m
KUBECONFIG="$kubeconfig" oc -n "$namespace" wait \
  --for=condition=complete job/database-migrate-4a6f4df --timeout=10m

KUBECONFIG="$kubeconfig" oc -n "$namespace" scale deployment/backend --replicas=1
KUBECONFIG="$kubeconfig" oc -n "$namespace" rollout status \
  deployment/backend --timeout=10m
KUBECONFIG="$kubeconfig" oc -n "$namespace" scale deployment/backend --replicas=2
KUBECONFIG="$kubeconfig" oc -n "$namespace" rollout status \
  deployment/backend --timeout=10m

available="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get deployment backend \
  -o jsonpath='{.status.availableReplicas}')"
[[ "$available" == "2" ]] || fail "backend has ${available:-0}/2 available replicas"

echo "Flightpath stage is ready with two backend replicas and no public Route."
