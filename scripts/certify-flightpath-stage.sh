#!/usr/bin/env bash
set -euo pipefail

namespace="launchpad-stage"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence_dir="$repo_root/evidence/runs/flightpath-stage"
port="15432"

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

available="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get deployment backend \
  -o jsonpath='{.status.availableReplicas}')"
[[ "$available" == "2" ]] || fail "backend has ${available:-0}/2 available replicas"

routes="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get routes \
  --no-headers 2>/dev/null | wc -l | tr -d ' ')"
[[ "$routes" == "0" ]] || fail "staging namespace unexpectedly has public Routes"

while IFS= read -r pod; do
  ready="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" exec "$pod" -- \
    python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8000/ready"))["status"])')"
  [[ "$ready" == "ready" ]] || fail "$pod readiness returned $ready"
done < <(KUBECONFIG="$kubeconfig" oc -n "$namespace" get pods \
  -l app.kubernetes.io/name=backend -o name)

mkdir -p "$evidence_dir"
forward_log="$(mktemp -t launchpad-stage-forward.XXXXXX)"
KUBECONFIG="$kubeconfig" oc -n "$namespace" port-forward \
  service/postgres "$port:5432" >"$forward_log" 2>&1 &
forward_pid=$!
cleanup() {
  kill "$forward_pid" >/dev/null 2>&1 || true
  rm -f "$forward_log"
}
trap cleanup EXIT

python3 - "$port" <<'PY'
import socket
import sys
import time

port = int(sys.argv[1])
for _ in range(100):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("PostgreSQL port-forward did not become ready")
PY

password_b64="$(KUBECONFIG="$kubeconfig" oc -n "$namespace" get secret \
  launchpad-db-secret -o jsonpath='{.data.POSTGRES_PASSWORD}')"
password="$(printf '%s' "$password_b64" | base64 --decode)"
unset password_b64

EVENT_TEST_DATABASE_URL="postgresql://launchpad_stage:${password}@127.0.0.1:${port}/launchpad_stage" \
PYTHONPATH="$repo_root:$repo_root/backend" \
  "$repo_root/.venv/bin/pytest" -q \
  "$repo_root/backend/tests/test_event_cleanup_postgres.py" \
  --junitxml="$evidence_dir/postgres-ha.xml"
unset password

echo "Flightpath stage PostgreSQL and two-replica certification passed."
