#!/usr/bin/env bash
set -uo pipefail

usage() {
  echo "usage: certify-september-17-exact-75.sh <agent-201-workshop-id> <multi-agent-workshop-id> <serve-llms-workshop-id> [result-dir]" >&2
}

if [[ "$#" -lt 3 || "$#" -gt 4 ]]; then
  usage
  exit 64
fi

agent_workshop_id="$1"
multi_workshop_id="$2"
serve_workshop_id="$3"
result_dir="${4:-/tmp/launchpad-september17-exact75-$(date -u +%Y%m%dT%H%M%SZ)}"
: "${KUBECONFIG:?KUBECONFIG must point to the Arena control-plane credential}"
: "${OC_REQUEST_TIMEOUT:=15s}"
: "${CORDON_ATTEMPTS:=12}"
: "${MULTI_POLICY_CONCURRENCY:=5}"
: "${MULTI_DEEP_CONCURRENCY:=5}"
: "${EXERCISE_RHGNR1:=false}"

for concurrency in "$MULTI_POLICY_CONCURRENCY" "$MULTI_DEEP_CONCURRENCY"; do
  [[ "$concurrency" =~ ^[1-9][0-9]*$ ]] || {
    echo "multi-agent concurrency values must be positive integers" >&2
    exit 64
  }
done
[[ "$EXERCISE_RHGNR1" == "false" || "$EXERCISE_RHGNR1" == "true" ]] || {
  echo "EXERCISE_RHGNR1 must be true or false" >&2
  exit 64
}

[[ ! -e "$result_dir" ]] || {
  echo "result directory already exists: $result_dir" >&2
  exit 73
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p \
  "$result_dir/agent-201" \
  "$result_dir/multi-agent/concurrent" \
  "$result_dir/multi-agent" \
  "$result_dir/serve-llms" \
  "$result_dir/policy-slots"
secret_work_dir="$(mktemp -d "${TMPDIR:-/tmp}/launchpad-exact75-secrets.XXXXXX")"
chmod 700 "$secret_work_dir"

# Keep every OpenShift operation pinned to Arena. Brutus is reached only by
# the backend's persisted remote client in certify-agent-201-via-control-plane.
oc() {
  if [[ "${1:-}" == "config" ]]; then
    command oc --kubeconfig "$KUBECONFIG" "$@"
  else
    command oc --kubeconfig "$KUBECONFIG" \
      --request-timeout="$OC_REQUEST_TIMEOUT" "$@"
  fi
}

router_restart_total() {
  oc -n openshift-ingress get pods \
    -l ingresscontroller.operator.openshift.io/deployment-ingresscontroller=default \
    -o json \
    | jq '[.items[].status.containerStatuses[]? | select(.name == "router") | .restartCount] | add // 0'
}

server="$(oc config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
if [[ "$server" != "https://api.arena.fm2aihpcsed.com:6443" ]]; then
  echo "refusing to run: expected Arena API, found '$server'" >&2
  exit 2
fi

discover_namespaces() {
  local workshop_id="${1:?workshop id is required}"
  local -a namespaces
  namespaces=( $(
    oc get namespaces \
      -l "launchpad.redhat.com/workshop-id=${workshop_id}" \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' \
      | sort
  ) )
  [[ "${#namespaces[@]}" -eq 25 ]] || {
    echo "workshop ${workshop_id} has ${#namespaces[@]} namespaces; expected 25" >&2
    return 3
  }
  printf '%s\n' "${namespaces[@]}"
}

recordon_rhgnr1() {
  local attempt
  for ((attempt = 1; attempt <= CORDON_ATTEMPTS; attempt++)); do
    if command oc --kubeconfig "$KUBECONFIG" --request-timeout=5s \
      adm cordon rhgnr1 >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  echo "failed to restore rhgnr1 cordon after ${CORDON_ATTEMPTS} attempts" >&2
  return 1
}

cleanup() {
  if [[ "$EXERCISE_RHGNR1" == "true" ]]; then
    recordon_rhgnr1 || true
  fi
  case "$secret_work_dir" in
    "${TMPDIR:-/tmp}"/launchpad-exact75-secrets.*)
      rm -rf -- "$secret_work_dir"
      ;;
  esac
}

trap cleanup EXIT

run_agent_201() {
  local backend_pod
  backend_pod="$(
    oc -n partner-ai-launchpad get pod \
      -l app.kubernetes.io/name=backend \
      -o jsonpath='{.items[0].metadata.name}'
  )"
  oc -n partner-ai-launchpad exec -i "$backend_pod" -- \
    env PYTHONWARNINGS=ignore python - \
      --workshop-id "$agent_workshop_id" \
      --cluster-id brutus \
      --setup-concurrency 5 \
      --journey-concurrency 25 \
      < "$script_dir/certify-agent-201-via-control-plane.py"
}

run_multi_concurrent_wave() {
  local -a namespaces pids
  local namespace host token config raw receipt pid fail=0
  namespaces=( "$@" )
  pids=()
  for namespace in "${namespaces[@]}"; do
    host="$(oc get route multi-agent -n "$namespace" -o jsonpath='{.spec.host}')"
    token="$(oc get secret multi-agent-runtime -n "$namespace" -o json | jq -r '.data.AGENT_AUTH_TOKEN | @base64d')"
    [[ -n "$host" && -n "$token" && "$token" != "null" ]] || return 4
    config="$secret_work_dir/${namespace}.curl"
    raw="$secret_work_dir/${namespace}.json"
    receipt="$result_dir/multi-agent/concurrent/${namespace}.json"
    umask 077
    printf 'header = "Authorization: Bearer %s"\n' "$token" >"$config"
    unset token
    (
      curl --config "$config" -fsSk \
        --retry 3 --retry-all-errors --retry-delay 2 \
        --connect-timeout 10 --max-time 500 \
        -H 'Content-Type: application/json' \
        -X POST "https://${host}/api/v1/workflow" \
        --data '{"query":"Look up record REC-001 and recommend next steps","workflow_type":"comprehensive"}' \
        >"$raw"
      jq -c '
        (
          .agents_involved == ["research", "analyst", "executor"]
          and (.steps | length) == 3
          and ([.steps[] | select(.result | contains("[MCP tool data retrieved]"))] | length) == 3
          and ([.steps[] | select(.result | startswith("Error:"))] | length) == 0
        ) as $passed
        | {
        result: (if $passed then "GREEN-live-participant-wave" else "RED-live-participant-wave" end),
        agents: .agents_involved,
        steps: (.steps | length),
        mcp_steps: [.steps[] | select(.result | contains("[MCP tool data retrieved]")) | .agent],
        errors: [.steps[] | select(.result | startswith("Error:")) | .agent],
        latency_ms: .total_latency_ms
      }' "$raw" >"$receipt"
      jq -e '
        .result == "GREEN-live-participant-wave"
        and .agents == ["research", "analyst", "executor"]
        and .steps == 3
        and (.mcp_steps | length) == 3
        and (.errors | length) == 0
      ' "$receipt" >/dev/null
    ) &
    pids+=($!)
  done
  for pid in "${pids[@]}"; do
    wait "$pid" || fail=$((fail + 1))
  done
  echo "multi_agent_concurrent_total=25 multi_agent_concurrent_failures=${fail}"
  [[ "$fail" -eq 0 ]]
}

run_multi_agent() {
  local -a namespaces pids
  local namespace pid batch index limit fail=0
  namespaces=( $(discover_namespaces "$multi_workshop_id") )
  [[ "${#namespaces[@]}" -eq 25 ]] || return 3
  run_multi_concurrent_wave "${namespaces[@]}" || return $?
  for ((batch = 0; batch < ${#namespaces[@]}; batch += MULTI_DEEP_CONCURRENCY)); do
    pids=()
    limit=$((batch + MULTI_DEEP_CONCURRENCY))
    if [[ "$limit" -gt "${#namespaces[@]}" ]]; then
      limit="${#namespaces[@]}"
    fi
    for ((index = batch; index < limit; index++)); do
      namespace="${namespaces[$index]}"
    env KUBECONFIG="$KUBECONFIG" \
      POLICY_CONCURRENCY="$MULTI_POLICY_CONCURRENCY" \
      POLICY_LOCK_DIR="$result_dir/policy-slots" \
      bash "$script_dir/certify-multi-agent-seat.sh" "$namespace" \
      >"$result_dir/multi-agent/${namespace}.json" 2>&1 &
    pids+=($!)
    done
    for pid in "${pids[@]}"; do
      wait "$pid" || fail=$((fail + 1))
    done
  done
  echo "multi_agent_total=25 multi_agent_failures=${fail}"
  [[ "$fail" -eq 0 ]]
}

run_serve_llms() {
  local -a namespaces pids
  local namespace pid fail=0
  namespaces=( $(discover_namespaces "$serve_workshop_id") )
  [[ "${#namespaces[@]}" -eq 25 ]] || return 3
  pids=()
  for namespace in "${namespaces[@]}"; do
    (
      env KUBECONFIG="$KUBECONFIG" \
        bash "$script_dir/certify-cpu-serving-seat.sh" "$namespace" arena
      oc wait -n "$namespace" \
        --for=condition=Available deployment/anythingllm \
        --timeout=300s >/dev/null
      env KUBECONFIG="$KUBECONFIG" \
        CERTIFICATION_RUN_ID="sep17-${namespace##*-}-$(date -u +%H%M%S)" \
        bash "$script_dir/certify-cpu-serving-rag.sh" "$namespace" arena
    ) >"$result_dir/serve-llms/${namespace}.tsv" 2>&1 &
    pids+=($!)
  done
  for pid in "${pids[@]}"; do
    wait "$pid" || fail=$((fail + 1))
  done
  echo "serve_llms_total=25 serve_llms_failures=${fail}"
  [[ "$fail" -eq 0 ]]
}

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
oc wait node/rhgnr1 --for=condition=Ready --timeout=60s >/dev/null
rhgnr1_unschedulable="$(oc get node rhgnr1 -o jsonpath='{.spec.unschedulable}')"
if [[ "$EXERCISE_RHGNR1" == "true" ]]; then
  oc adm uncordon rhgnr1 >/dev/null
else
  [[ "$rhgnr1_unschedulable" == "true" ]] || {
    echo "refusing protected run: rhgnr1 must already be cordoned" >&2
    exit 5
  }
fi
router_restarts_before="$(router_restart_total)"

run_agent_201 >"$result_dir/agent-201/run.log" 2>&1 &
agent_pid=$!
run_multi_agent >"$result_dir/multi-agent/run.log" 2>&1 &
multi_pid=$!
run_serve_llms >"$result_dir/serve-llms/run.log" 2>&1 &
serve_pid=$!

# Multi-Agent intentionally restarts seat workloads. Restore the scheduling
# guard immediately only when this run explicitly exercised rhgnr1.
wait "$multi_pid"
multi_rc=$?
if [[ "$EXERCISE_RHGNR1" == "true" ]]; then
  recordon_rhgnr1
fi
wait "$agent_pid"
agent_rc=$?
wait "$serve_pid"
serve_rc=$?
completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
router_restarts_after="$(router_restart_total)"
router_restart_increase=$((router_restarts_after - router_restarts_before))

agent_receipt="$(grep '^{' "$result_dir/agent-201/run.log" | tail -n 1)"
agent_passed=0
if [[ -n "$agent_receipt" ]] \
  && printf '%s' "$agent_receipt" | jq -e ".journeys.passed | numbers" >/dev/null 2>&1; then
  agent_passed="$(printf '%s' "$agent_receipt" | jq -r '.journeys.passed')"
fi
multi_passed="$(rg -l '"result":"GREEN-live-internal-seat"' "$result_dir"/multi-agent/launchpad-*.json 2>/dev/null | wc -l | tr -d ' ')"
multi_concurrent_passed="$(rg -l '"result":"GREEN-live-participant-wave"' "$result_dir"/multi-agent/concurrent/launchpad-*.json 2>/dev/null | wc -l | tr -d ' ')"
serve_passed="$(rg -l 'grounded=true' "$result_dir"/serve-llms/launchpad-*.tsv 2>/dev/null | wc -l | tr -d ' ')"
total_passed=$((agent_passed + multi_passed + serve_passed))

if [[ "$agent_rc" -eq 0 && "$multi_rc" -eq 0 && "$serve_rc" -eq 0 \
  && "$total_passed" -eq 75 && "$multi_concurrent_passed" -eq 25 \
  && "$router_restart_increase" -eq 0 ]]; then
  status="passed"
  exit_code=0
else
  status="failed"
  exit_code=1
fi

jq -n \
  --arg status "$status" \
  --arg started_at "$started_at" \
  --arg completed_at "$completed_at" \
  --arg result_dir "$result_dir" \
  --arg agent_workshop_id "$agent_workshop_id" \
  --arg multi_workshop_id "$multi_workshop_id" \
  --arg serve_workshop_id "$serve_workshop_id" \
  --argjson agent_passed "$agent_passed" \
  --argjson multi_passed "$multi_passed" \
  --argjson multi_concurrent_passed "$multi_concurrent_passed" \
  --argjson serve_passed "$serve_passed" \
  --argjson agent_rc "$agent_rc" \
  --argjson multi_rc "$multi_rc" \
  --argjson serve_rc "$serve_rc" \
  --argjson router_restarts_before "$router_restarts_before" \
  --argjson router_restarts_after "$router_restarts_after" \
  --argjson router_restart_increase "$router_restart_increase" \
  --arg exercise_rhgnr1 "$EXERCISE_RHGNR1" \
  '{
    "status": $status,
    "started_at": $started_at,
    "completed_at": $completed_at,
    "participants_started": 75,
    "participants_passed": ($agent_passed + $multi_passed + $serve_passed),
    "contains_plaintext_credentials": false,
    "return_codes": {
      "agent_201": $agent_rc,
      "multi_agent": $multi_rc,
      "serve_llms": $serve_rc
    },
    "resilience": {
      "exercise_rhgnr1": ($exercise_rhgnr1 == "true"),
      "router_restarts_before": $router_restarts_before,
      "router_restarts_after": $router_restarts_after,
      "router_restart_increase": $router_restart_increase
    },
    "result_dir": $result_dir,
    "workshops": {
      "agent_201": {"id": $agent_workshop_id, "passed": $agent_passed},
      "multi_agent": {"id": $multi_workshop_id, "passed": $multi_passed, "concurrent_wave_passed": $multi_concurrent_passed},
      "serve_llms": {"id": $serve_workshop_id, "passed": $serve_passed}
    }
  }' | tee "$result_dir/summary.json"

exit "$exit_code"
