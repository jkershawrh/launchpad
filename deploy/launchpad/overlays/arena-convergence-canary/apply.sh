#!/usr/bin/env bash
set -euo pipefail

namespace="partner-ai-launchpad"
candidate="launchpad-staging-20260922-02"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
overlay="$root/deploy/launchpad/overlays/arena-convergence-canary"
catalog_root="$root/deploy/launchpad/overlays/flightpath-candidate"

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ $# -eq 2 ]] || fail "usage: $0 /explicit/arena.kubeconfig --confirm-candidate=$candidate"
kubeconfig="$1"
confirmation="$2"
[[ -f "$kubeconfig" ]] || fail "Arena kubeconfig is not a file"
[[ "$confirmation" == "--confirm-candidate=$candidate" ]] || fail "candidate confirmation does not match"

server="$(KUBECONFIG="$kubeconfig" oc whoami --show-server)"
[[ "$server" == *"api.arena.fm2aihpcsed.com"* ]] || fail "kubeconfig is not Arena: $server"

for mapping in \
  "convergence-intel-llm-cpu-serving-catalog:intel-llm-cpu-serving.catalog-item.yaml" \
  "convergence-intel-xeon6-agent-201-catalog:intel-xeon6-agent-201.catalog-item.yaml" \
  "convergence-multi-agent-quickstart-catalog:multi-agent-quickstart.catalog-item.yaml"; do
  name="${mapping%%:*}"
  source="${mapping#*:}"
  KUBECONFIG="$kubeconfig" oc -n "$namespace" create configmap "$name" \
    --from-file="catalog-item.yaml=$catalog_root/$source" \
    --dry-run=client -o yaml \
    | KUBECONFIG="$kubeconfig" oc apply -f -
done

KUBECONFIG="$kubeconfig" oc apply -k "$overlay"
KUBECONFIG="$kubeconfig" oc -n "$namespace" rollout status deployment/backend --timeout=10m
KUBECONFIG="$kubeconfig" oc -n "$namespace" rollout status deployment/lifecycle-worker --timeout=10m

available="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get deployment backend -o jsonpath='{.status.availableReplicas}')"
[[ "$available" == "2" ]] || fail "backend has ${available:-0}/2 available replicas"

echo "Arena convergence candidate $candidate is deployed with two available backend replicas."
