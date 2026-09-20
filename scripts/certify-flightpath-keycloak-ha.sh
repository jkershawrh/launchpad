#!/usr/bin/env bash
set -euo pipefail

namespace="launchpad-stage"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence_dir="$repo_root/evidence/runs/flightpath-stage"
http_port="18087"
management_port="19000"

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

pods=()
while IFS= read -r pod; do
  [[ -z "$pod" ]] || pods+=("$pod")
done < <(KUBECONFIG="$kubeconfig" oc -n "$namespace" get pods \
  -l app.kubernetes.io/name=keycloak -o json \
  | jq -r '.items[]
      | select(any(.status.conditions[]?;
          .type == "Ready" and .status == "True"))
      | .metadata.name')
[[ "${#pods[@]}" -eq 2 ]] || fail "expected two ready Keycloak pods"

nodes=()
while IFS= read -r node; do
  [[ -z "$node" ]] || nodes+=("$node")
done < <(KUBECONFIG="$kubeconfig" oc -n "$namespace" get pods \
  -l app.kubernetes.io/name=keycloak \
  -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' | sort -u)
[[ "${#nodes[@]}" -eq 2 ]] || fail "Keycloak replicas do not span two nodes"

routes="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get routes \
  --no-headers 2>/dev/null | wc -l | tr -d ' ')"
[[ "$routes" == "0" ]] || fail "staging namespace unexpectedly has public Routes"

survivor="${pods[0]}"
victim="${pods[1]}"
forward_log="$(mktemp -t launchpad-stage-keycloak-forward.XXXXXX)"
KUBECONFIG="$kubeconfig" oc -n "$namespace" port-forward \
  "pod/$survivor" "$http_port:8080" "$management_port:9000" \
  >"$forward_log" 2>&1 &
forward_pid=$!
cleanup() {
  kill "$forward_pid" >/dev/null 2>&1 || true
  wait "$forward_pid" >/dev/null 2>&1 || true
  unlink "$forward_log" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in {1..60}; do
  curl -fsS "http://127.0.0.1:${management_port}/health/ready" >/dev/null \
    && break
  sleep 1
done
kill -0 "$forward_pid" 2>/dev/null || fail "Keycloak port-forward failed"
curl -fsS "http://127.0.0.1:${management_port}/health/ready" >/dev/null \
  || fail "surviving Keycloak replica is not ready"

admin_user="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get secret \
  keycloak-stage-bootstrap -o jsonpath='{.data.username}' | base64 --decode)"
admin_password="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get secret \
  keycloak-stage-bootstrap -o jsonpath='{.data.password}' | base64 --decode)"
admin_token="$(printf \
  'client_id=admin-cli&username=%s&password=%s&grant_type=password' \
  "$admin_user" "$admin_password" \
  | curl -fsS \
    "http://127.0.0.1:${http_port}/realms/master/protocol/openid-connect/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-binary @- \
  | jq -r .access_token)"
unset admin_password
[[ -n "$admin_token" && "$admin_token" != "null" ]] \
  || fail "Keycloak admin token was not issued"

provider_count="$(curl -fsS \
  "http://127.0.0.1:${http_port}/admin/serverinfo" \
  -H "Authorization: Bearer $admin_token" \
  | jq '[.. | objects | select(.id? == "launchpad-order-code")] | length')"
[[ "$provider_count" -ge 1 ]] \
  || fail "launchpad-order-code authenticator is not registered"

KUBECONFIG="$kubeconfig" oc -n "$namespace" delete pod "$victim" \
  --wait=false >/dev/null
failures=0
checks=40
for _ in $(seq 1 "$checks"); do
  if ! curl -fsS "http://127.0.0.1:${http_port}/realms/master" >/dev/null; then
    failures=$((failures + 1))
  fi
  sleep 0.25
done
[[ "$failures" -eq 0 ]] || fail "$failures/$checks survivor checks failed"

KUBECONFIG="$kubeconfig" oc -n "$namespace" rollout status \
  deployment/keycloak --timeout=10m
available="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get deployment keycloak \
  -o jsonpath='{.status.availableReplicas}')"
[[ "$available" == "2" ]] || fail "Keycloak recovered only ${available:-0}/2 replicas"

image="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get deployment keycloak \
  -o jsonpath='{.spec.template.spec.containers[0].image}')"
generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$evidence_dir"
jq -n \
  --arg generated_at "$generated_at" \
  --arg image "$image" \
  --arg survivor "$survivor" \
  --arg victim "$victim" \
  --argjson checks "$checks" \
  --argjson failures "$failures" \
  --argjson provider_count "$provider_count" \
  '{
    evidence_id: "flightpath-stage-keycloak-ha-20260920",
    generated_at: $generated_at,
    stage: "GREEN-integration",
    cluster: "flightpath",
    namespace: "launchpad-stage",
    public_routes: 0,
    image: $image,
    replicas_ready_after_fault: 2,
    fault: {
      deleted_pod: $victim,
      surviving_pod: $survivor,
      checks: $checks,
      failures: $failures
    },
    custom_authenticator_factories: $provider_count,
    boundary: [
      "No public Route or DNS was created",
      "No production tunnel token was used",
      "No participant or retained workshop state was accessed",
      "Realm, client, browser journey, and connector failover remain unproved"
    ]
  }' >"$evidence_dir/keycloak-ha.json"
unset admin_token admin_user

echo "Flightpath stage Keycloak replica-loss certification passed."
