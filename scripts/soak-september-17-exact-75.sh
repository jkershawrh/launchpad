#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: soak-september-17-exact-75.sh <agent-201-workshop-id> <multi-agent-workshop-id> <serve-llms-workshop-id> [result-dir]" >&2
}

if [[ "$#" -lt 3 || "$#" -gt 4 ]]; then
  usage
  exit 64
fi

agent_workshop_id="$1"
multi_workshop_id="$2"
serve_workshop_id="$3"
result_dir="${4:-/tmp/launchpad-september17-exact75-soak-$(date -u +%Y%m%dT%H%M%SZ)}"
: "${KUBECONFIG:?KUBECONFIG must point to the Arena control-plane credential}"
SOAK_DURATION_SECONDS="${SOAK_DURATION_SECONDS:-3600}"
SOAK_INTERVAL_SECONDS="${SOAK_INTERVAL_SECONDS:-60}"
SOAK_PROBE_CONCURRENCY="${SOAK_PROBE_CONCURRENCY:-15}"
SOAK_API_PORT="${SOAK_API_PORT:-18106}"

for value in "$SOAK_DURATION_SECONDS" "$SOAK_INTERVAL_SECONDS" "$SOAK_PROBE_CONCURRENCY" "$SOAK_API_PORT"; do
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || {
    echo "soak configuration values must be positive integers" >&2
    exit 64
  }
done

[[ ! -e "$result_dir" ]] || {
  echo "result directory already exists: $result_dir" >&2
  exit 73
}
mkdir -p "$result_dir"

oc() {
  command oc --kubeconfig "$KUBECONFIG" --request-timeout=20s "$@"
}

server="$(command oc --kubeconfig "$KUBECONFIG" config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
if [[ "$server" != "https://api.arena.fm2aihpcsed.com:6443" ]]; then
  echo "refusing to run: expected Arena API, found '$server'" >&2
  exit 2
fi

secret_work_dir="$(mktemp -d "${TMPDIR:-/tmp}/launchpad-exact75-soak-secrets.XXXXXX")"
chmod 700 "$secret_work_dir"
port_forward_pid=""

cleanup() {
  if [[ -n "$port_forward_pid" ]]; then
    kill "$port_forward_pid" >/dev/null 2>&1 || true
  fi
  case "$secret_work_dir" in
    "${TMPDIR:-/tmp}"/launchpad-exact75-soak-secrets.*)
      rm -rf -- "$secret_work_dir"
      ;;
  esac
}
trap cleanup EXIT

admin_key="$(
  oc -n partner-ai-launchpad get secret launchpad-api-keys \
    -o jsonpath='{.data.admin}' | base64 -d
)"
umask 077
printf 'header = "X-API-Key: %s"\n' "$admin_key" >"$secret_work_dir/api.curl"
unset admin_key

oc -n partner-ai-launchpad port-forward service/backend "$SOAK_API_PORT:8000" \
  >"$secret_work_dir/port-forward.log" 2>&1 &
port_forward_pid=$!
api_base="http://127.0.0.1:${SOAK_API_PORT}"
for _ in {1..30}; do
  if curl -fsS --max-time 2 "$api_base/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 "$api_base/health" >/dev/null

api() {
  curl --config "$secret_work_dir/api.curl" -fsS --max-time 20 "$api_base$1"
}

arena_namespaces="$({
  oc get namespaces -l "launchpad.redhat.com/workshop-id=${multi_workshop_id}" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
  oc get namespaces -l "launchpad.redhat.com/workshop-id=${serve_workshop_id}" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
} | jq -Rsc 'split("\n") | map(select(length > 0)) | unique')"
[[ "$(jq 'length' <<<"$arena_namespaces")" -eq 50 ]] || {
  echo "expected 50 Arena workshop namespaces" >&2
  exit 3
}

snapshots="$result_dir/snapshots.jsonl"
: >"$snapshots"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
started_epoch="$(date +%s)"
end_epoch=$((started_epoch + SOAK_DURATION_SECONDS))
sample_number=0
failure_samples=0
first_restart_total=""
max_restart_total=0

while :; do
  sample_number=$((sample_number + 1))
  sampled_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  agent_json="$(api "/api/v1/workshops/${agent_workshop_id}")"
  multi_json="$(api "/api/v1/workshops/${multi_workshop_id}")"
  serve_json="$(api "/api/v1/workshops/${serve_workshop_id}")"
  workshop_summary="$(
    printf '%s\n%s\n%s\n' "$agent_json" "$multi_json" "$serve_json" | jq -sc '
      {
        workshops: map({
          workshop_id,
          status,
          cluster_ref,
          ready_seats: ([.seats[] | select(.status == "ready")] | length),
          total_seats: (.seats | length)
        }),
        all_workshops_ready: all(.[];
          .status == "ready"
          and (.seats | length) == 25
          and ([.seats[] | select(.status == "ready")] | length) == 25
        )
      }
    '
  )"

  printf '%s\n%s\n%s\n' "$agent_json" "$multi_json" "$serve_json" \
    | jq -r '.seats[].showroom_url' >"$secret_work_dir/showroom-urls"
  xargs -P "$SOAK_PROBE_CONCURRENCY" -n 1 sh -c '
    url="$1"
    code="$(curl -kLsS --retry 2 --retry-all-errors --retry-delay 1 \
      --connect-timeout 5 --max-time 15 -o /dev/null -w "%{http_code}" \
      "${url}/" 2>/dev/null || true)"
    printf "%s\n" "${code:-000}"
  ' sh <"$secret_work_dir/showroom-urls" >"$secret_work_dir/showroom-codes"
  showroom_total="$(wc -l <"$secret_work_dir/showroom-codes" | tr -d ' ')"
  showroom_http_200="$(grep -c '^200$' "$secret_work_dir/showroom-codes" || true)"

  pod_summary="$(
    oc get pods -A -o json | jq -c --argjson namespaces "$arena_namespaces" '
      [.items[]
        | select(.metadata.deletionTimestamp == null)
        | select(.metadata.namespace as $namespace
          | ($namespaces | index($namespace)) != null)
      ] as $pods
      | {
          arena_pod_total: ($pods | length),
          arena_unready_pods: ([$pods[] | select(
            .status.phase != "Running"
            or (.status.containerStatuses | length) == 0
            or any(.status.containerStatuses[]; .ready != true)
          )] | length),
          arena_restart_total: ([$pods[].status.containerStatuses[]?.restartCount] | add // 0)
        }
    '
  )"
  restart_total="$(jq -r '.arena_restart_total' <<<"$pod_summary")"
  if [[ -z "$first_restart_total" ]]; then
    first_restart_total="$restart_total"
  fi
  if [[ "$restart_total" -gt "$max_restart_total" ]]; then
    max_restart_total="$restart_total"
  fi

  node_summary="$(oc get nodes -o json | jq -c '
    {
      arena_node_total: (.items | length),
      arena_unready_nodes: ([.items[] | select(
        ([.status.conditions[] | select(.type == "Ready") | .status][0]) != "True"
      )] | length)
    }
  ')"

  worker_pod="$(
    oc -n partner-ai-launchpad get pod -l app.kubernetes.io/name=lifecycle-worker \
      -o jsonpath='{.items[0].metadata.name}'
  )"
  granite_tools_http="$(
    oc -n partner-ai-launchpad exec "$worker_pod" -- python -c \
      'import urllib.request; print(urllib.request.urlopen("http://vllm-granite-3-2-8b-tools.fleet-llm-d.svc:8080/v1/models", timeout=10).status)' \
      2>/dev/null || echo 000
  )"
  nomic_embed_http="$(
    oc -n partner-ai-launchpad exec "$worker_pod" -- python -c \
      'import urllib.request; print(urllib.request.urlopen("http://tei-nomic-embed.fleet-llm-d.svc:8080/info", timeout=10).status)' \
      2>/dev/null || echo 000
  )"

  all_workshops_ready="$(jq -r '.all_workshops_ready' <<<"$workshop_summary")"
  arena_pod_total="$(jq -r '.arena_pod_total' <<<"$pod_summary")"
  arena_unready_pods="$(jq -r '.arena_unready_pods' <<<"$pod_summary")"
  arena_unready_nodes="$(jq -r '.arena_unready_nodes' <<<"$node_summary")"
  sample_passed=false
  if [[ "$all_workshops_ready" == "true" \
    && "$showroom_total" -eq 75 \
    && "$showroom_http_200" -eq 75 \
    && "$arena_pod_total" -ge 75 \
    && "$arena_unready_pods" -eq 0 \
    && "$arena_unready_nodes" -eq 0 \
    && "$granite_tools_http" == "200" \
    && "$nomic_embed_http" == "200" ]]; then
    sample_passed=true
  else
    failure_samples=$((failure_samples + 1))
  fi

  jq -cn \
    --argjson sample "$sample_number" \
    --arg sampled_at "$sampled_at" \
    --argjson workshops "$workshop_summary" \
    --argjson showroom_total "$showroom_total" \
    --argjson showroom_http_200 "$showroom_http_200" \
    --argjson pods "$pod_summary" \
    --argjson nodes "$node_summary" \
    --arg granite_tools_http "$granite_tools_http" \
    --arg nomic_embed_http "$nomic_embed_http" \
    --argjson passed "$sample_passed" \
    '{
      sample: $sample,
      sampled_at: $sampled_at,
      passed: $passed,
      workshop_state: $workshops,
      showroom_total: $showroom_total,
      showroom_http_200: $showroom_http_200,
      arena_pods: $pods,
      arena_nodes: $nodes,
      granite_tools_http: $granite_tools_http,
      nomic_embed_http: $nomic_embed_http,
      contains_plaintext_credentials: false
    }' >>"$snapshots"

  printf '%s sample=%d passed=%s showrooms=%s/%s unready_pods=%s restarts=%s unready_nodes=%s models=%s/%s\n' \
    "$sampled_at" "$sample_number" "$sample_passed" "$showroom_http_200" "$showroom_total" \
    "$arena_unready_pods" "$restart_total" "$arena_unready_nodes" \
    "$granite_tools_http" "$nomic_embed_http"

  now_epoch="$(date +%s)"
  if [[ "$now_epoch" -ge "$end_epoch" ]]; then
    break
  fi
  remaining=$((end_epoch - now_epoch))
  sleep_seconds="$SOAK_INTERVAL_SECONDS"
  if [[ "$remaining" -lt "$sleep_seconds" ]]; then
    sleep_seconds="$remaining"
  fi
  sleep "$sleep_seconds"
done

completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
completed_epoch="$(date +%s)"
duration_observed=$((completed_epoch - started_epoch))
result="GREEN-live-sixty-minute-soak"
exit_code=0
if [[ "$failure_samples" -ne 0 ]]; then
  result="RED-live-sixty-minute-soak"
  exit_code=1
fi

jq -n \
  --arg result "$result" \
  --arg started_at "$started_at" \
  --arg completed_at "$completed_at" \
  --arg agent_workshop_id "$agent_workshop_id" \
  --arg multi_workshop_id "$multi_workshop_id" \
  --arg serve_workshop_id "$serve_workshop_id" \
  --arg source_commit "$(git rev-parse HEAD)" \
  --argjson duration_observed_seconds "$duration_observed" \
  --argjson samples "$sample_number" \
  --argjson failed_samples "$failure_samples" \
  --argjson first_restart_total "$first_restart_total" \
  --argjson max_restart_total "$max_restart_total" \
  '{
    schema: "launchpad.redhat.com/exact75-soak/v1",
    result: $result,
    started_at: $started_at,
    completed_at: $completed_at,
    duration_observed_seconds: $duration_observed_seconds,
    samples: $samples,
    failed_samples: $failed_samples,
    arena_restart_total: {
      first: $first_restart_total,
      maximum: $max_restart_total,
      increase: ($max_restart_total - $first_restart_total)
    },
    workshops: {
      agent_201: {id: $agent_workshop_id, cluster_ref: "brutus", seats: 25},
      multi_agent: {id: $multi_workshop_id, cluster_ref: "arena", seats: 25},
      serve_llms: {id: $serve_workshop_id, cluster_ref: "arena", seats: 25}
    },
    source_commit: $source_commit,
    snapshots: "snapshots.jsonl",
    contains_plaintext_credentials: false,
    default_kube_context_changed: false
  }' | tee "$result_dir/summary.json"

shasum -a 256 "$snapshots" >"$result_dir/snapshots.jsonl.sha256"
shasum -a 256 "$result_dir/summary.json" >"$result_dir/summary.json.sha256"
exit "$exit_code"
