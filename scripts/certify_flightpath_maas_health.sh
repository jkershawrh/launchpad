#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ $# -ge 3 && $# -le 4 ]] || fail \
  "usage: $0 KUBECONFIG NAMESPACE EXPECTED_BACKEND_DIGEST [INTERVAL_SECONDS]"

cluster_kubeconfig="$1"
namespace="$2"
expected_digest="$3"
interval_seconds="${4:-130}"

[[ -f "$cluster_kubeconfig" ]] || fail "kubeconfig is not a file"
[[ "$namespace" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] \
  || fail "namespace is invalid"
[[ "$expected_digest" =~ ^sha256:[a-f0-9]{64}$ ]] \
  || fail "expected backend digest is invalid"
[[ "$interval_seconds" =~ ^[0-9]+$ && "$interval_seconds" -ge 1 ]] \
  || fail "interval must be a positive integer"

server="$(KUBECONFIG="$cluster_kubeconfig" oc whoami --show-server)"
[[ "$server" == "https://api.flightpath.fm2aihpcsed.com:6443" ]] \
  || fail "target is not Flightpath"

backend_image="$(KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" get deployment backend \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="backend")].image}')"
[[ "$backend_image" == *@"$expected_digest" ]] \
  || fail "backend is not running the expected immutable digest"

KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" rollout status deployment/backend \
  --timeout=5m >/dev/null

for check in 1 2 3; do
  KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" exec deployment/backend -c backend -- \
    python3 -c '
import os
import httpx

base = os.environ["LITELLM_API_BASE"].rstrip("/")
key = os.environ["LITELLM_API_KEY"]
response = httpx.get(
    f"{base}/models",
    headers={"Authorization": f"Bearer {key}"},
    timeout=10,
)
response.raise_for_status()
models = response.json().get("data", [])
if not models or any(not item.get("id") for item in models):
    raise SystemExit("model inventory is empty or malformed")
' >/dev/null
  echo "PASS: authenticated Candidate MaaS inventory check $check/3"
  [[ "$check" -eq 3 ]] || sleep "$interval_seconds"
done

backend_logs="$(KUBECONFIG="$cluster_kubeconfig" oc -n "$namespace" logs deployment/backend \
  -c backend --tail=2000)"
if grep -Eq 'LiteLLM unreachable.*401 Unauthorized|Authorization: Bearer' <<<"$backend_logs"; then
  fail "backend logs contain an authorization failure or credential-bearing output"
fi

health_successes="$(grep -c 'Model health: checked' <<<"$backend_logs" || true)"
[[ "$health_successes" -ge 3 ]] \
  || fail "fewer than three scheduled model-health intervals were observed"

echo "Flightpath Candidate MaaS health certification: GREEN"
