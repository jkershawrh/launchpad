#!/usr/bin/env bash
set -euo pipefail

# Deterministic Arena workshop process-HA proof.
#
# The certifier creates one internal workshop, deletes the lifecycle worker
# owning the aggregate provision job, proves fenced takeover on the other
# node, validates every seat, and repeats the fault during aggregate reclaim.
# It never drains or reboots a node and it always restores a node it cordons.

usage() {
  echo "usage: $0 /absolute/arena.kubeconfig --confirm-worker-deletion 5|25" >&2
  exit 2
}

[[ $# -eq 3 ]] || usage
KUBECONFIG_PATH="$1"
[[ "$2" == "--confirm-worker-deletion" ]] || usage
SEAT_COUNT="$3"
[[ "$SEAT_COUNT" == "5" || "$SEAT_COUNT" == "25" ]] || {
  echo "SEAT_COUNT must be 5 or 25" >&2
  exit 2
}
[[ "$KUBECONFIG_PATH" == /* && -f "$KUBECONFIG_PATH" ]] || {
  echo "Arena kubeconfig must be an explicit absolute file" >&2
  exit 2
}

NAMESPACE="partner-ai-launchpad"
TENANT_ID="${TENANT_ID:-ha-cert-tenant}"
CATALOG_ITEM_ID="${CATALOG_ITEM_ID:-intel-llm-cpu-serving}"
OWNER_ID="${OWNER_ID:-arena-workshop-ha-certifier}"
LOCAL_PORT="${LOCAL_PORT:-18103}"
API_BASE="http://127.0.0.1:${LOCAL_PORT}"
DEFAULT_OUTPUT_PATH="evidence/runs/arena-lifecycle-${SEAT_COUNT}-seat-cross-node-workshop-ha-$(date -u +%Y%m%dT%H%M%SZ).json"
OUTPUT_PATH="${OUTPUT_PATH:-$DEFAULT_OUTPUT_PATH}"
PUBLIC_CERT_NAMESPACE="launchpad-public-cert-tenant-intel-llm-cpu-serv-205782"
WORKSHOP_ID_LABEL="launchpad.redhat.com/workshop-id"

OC=(oc --kubeconfig "$KUBECONFIG_PATH")
PF_PID=""
CERT_TMP="$(mktemp -d)"
PF_LOG="$CERT_TMP/backend-port-forward.log"
HELD_APPLICATIONS="$CERT_TMP/held-applications.tsv"
SEAT_PROOF_LINES="$CERT_TMP/seat-proofs.jsonl"
WORKSHOP_ID=""
RECLAIM_COMPLETED="false"
ADMIN_KEY=""
CORDONED_NODE=""

api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -fsS -X "$method" \
      -H "X-API-Key: $ADMIN_KEY" \
      -H "Content-Type: application/json" \
      --data "$body" \
      "$API_BASE$path"
  else
    curl -fsS -X "$method" -H "X-API-Key: $ADMIN_KEY" "$API_BASE$path"
  fi
}

api_idempotent_post() {
  local path="$1"
  local key="$2"
  local body="$3"
  curl -fsS -X POST \
    -H "X-API-Key: $ADMIN_KEY" \
    -H "Idempotency-Key: $key" \
    -H "Content-Type: application/json" \
    --data "$body" \
    "$API_BASE$path"
}

queue_reclaim_best_effort() {
  if [[ -n "$WORKSHOP_ID" && "$RECLAIM_COMPLETED" != "true" && -n "$PF_PID" ]]; then
    api DELETE "/api/v1/workshops/$WORKSHOP_ID" >/dev/null 2>&1 || true
  fi
}

restore_cordoned_node() {
  if [[ -n "$CORDONED_NODE" ]]; then
    "${OC[@]}" adm uncordon "$CORDONED_NODE" >/dev/null
    CORDONED_NODE=""
  fi
}

release_showroom_application_holds() {
  [[ -s "$HELD_APPLICATIONS" ]] || return 0
  local application_namespace application_name application finalizers filtered
  while IFS=$'\t' read -r application_namespace application_name; do
    [[ -n "$application_namespace" && -n "$application_name" ]] || continue
    application="$("${OC[@]}" -n "$application_namespace" get \
      application.argoproj.io "$application_name" -o json 2>/dev/null || true)"
    if [[ -n "$application" ]]; then
      finalizers="$(jq -c '.metadata.finalizers // []' <<<"$application")"
      filtered="$(jq -c \
        '[.[] | select(. != "launchpad.redhat.com/certification-hold")]' \
        <<<"$finalizers")"
      "${OC[@]}" -n "$application_namespace" patch \
        application.argoproj.io "$application_name" --type=merge \
        -p "{\"metadata\":{\"finalizers\":$filtered}}" >/dev/null || true
    fi
  done <"$HELD_APPLICATIONS"
  : >"$HELD_APPLICATIONS"
}

hold_showroom_applications() {
  local seat_proofs="$1"
  local session_namespace application_ref application_namespace application_name
  local application finalizers held_finalizers
  : >"$HELD_APPLICATIONS"
  while IFS= read -r session_namespace; do
    application_ref="$("${OC[@]}" get applications.argoproj.io -A -o json \
      | jq -r --arg namespace "$session_namespace" \
        '.items[] | select(.spec.destination.namespace == $namespace) | [.metadata.namespace,.metadata.name] | @tsv' \
      | head -n 1)"
    [[ -n "$application_ref" ]] || {
      echo "Could not find the Showroom Application for $session_namespace" >&2
      return 1
    }
    IFS=$'\t' read -r application_namespace application_name <<<"$application_ref"
    application="$("${OC[@]}" -n "$application_namespace" get \
      application.argoproj.io "$application_name" -o json)"
    finalizers="$(jq -c '.metadata.finalizers // []' <<<"$application")"
    held_finalizers="$(jq -c \
      '. + ["launchpad.redhat.com/certification-hold"] | unique' \
      <<<"$finalizers")"
    "${OC[@]}" -n "$application_namespace" patch \
      application.argoproj.io "$application_name" --type=merge \
      -p "{\"metadata\":{\"finalizers\":$held_finalizers}}" >/dev/null
    printf '%s\t%s\n' "$application_namespace" "$application_name" \
      >>"$HELD_APPLICATIONS"
  done < <(jq -r '.[].namespace' <<<"$seat_proofs")
  [[ "$(wc -l <"$HELD_APPLICATIONS" | tr -d ' ')" == "$SEAT_COUNT" ]] || {
    echo "Did not hold one Showroom Application per workshop seat" >&2
    return 1
  }
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  release_showroom_application_holds >/dev/null 2>&1 || true
  restore_cordoned_node >/dev/null 2>&1 || true
  queue_reclaim_best_effort
  if [[ -n "$PF_PID" ]]; then
    kill "$PF_PID" >/dev/null 2>&1 || true
    wait "$PF_PID" >/dev/null 2>&1 || true
  fi
  ADMIN_KEY=""
  if [[ "$CERT_TMP" == /tmp/* || "$CERT_TMP" == /var/folders/* ]]; then
    rm -f "$PF_LOG" "$HELD_APPLICATIONS" "$SEAT_PROOF_LINES"
    rmdir "$CERT_TMP" >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

now_epoch() {
  python3 -c 'import time; print(time.time())'
}

elapsed() {
  python3 - "$1" "$2" <<'PY'
import sys
print(round(float(sys.argv[2]) - float(sys.argv[1]), 3))
PY
}

job_json() {
  local job_id="$1"
  [[ "$job_id" =~ ^[0-9a-f-]{36}$ ]] || {
    echo "Refusing unsafe lifecycle job identifier" >&2
    return 2
  }
  "${OC[@]}" -n "$NAMESPACE" exec deployment/postgres -- \
    psql -U launchpad -d launchpad -tA -c \
    "SELECT json_build_object('operation', operation, 'status', status, 'owner_id', owner_id, 'fencing_token', fencing_token, 'attempts', attempts, 'step', step, 'last_error', last_error)::text FROM lifecycle_jobs WHERE job_id = '$job_id';"
}

wait_for_claim() {
  local job_id="$1"
  local expected_operation="$2"
  local deadline=$((SECONDS + 90))
  local row status owner operation
  while (( SECONDS < deadline )); do
    row="$(job_json "$job_id")"
    status="$(jq -r '.status // empty' <<<"$row")"
    owner="$(jq -r '.owner_id // empty' <<<"$row")"
    operation="$(jq -r '.operation // empty' <<<"$row")"
    [[ -z "$operation" || "$operation" == "$expected_operation" ]] || {
      echo "Job $job_id is $operation, not $expected_operation" >&2
      return 1
    }
    if [[ "$status" == "running" && -n "$owner" ]]; then
      printf '%s' "$row"
      return 0
    fi
    if [[ "$status" == "succeeded" || "$status" == "failed" ]]; then
      echo "Job $job_id reached $status before fault injection" >&2
      return 1
    fi
    sleep 0.25
  done
  echo "Timed out waiting for job $job_id ownership" >&2
  return 1
}

owner_pod() {
  local owner_id="$1"
  local pod
  while IFS= read -r pod; do
    if [[ "$owner_id" == "$pod"-* ]]; then
      printf '%s' "$pod"
      return 0
    fi
  done < <("${OC[@]}" -n "$NAMESPACE" get pods \
    -l app.kubernetes.io/name=lifecycle-worker \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
  echo "Could not map lifecycle owner $owner_id to a running pod" >&2
  return 1
}

owner_node() {
  local owner_id="$1"
  local pod
  pod="$(owner_pod "$owner_id")"
  "${OC[@]}" -n "$NAMESPACE" get pod "$pod" -o jsonpath='{.spec.nodeName}'
}

cordon_owner_node() {
  local owner_id="$1"
  [[ -z "$CORDONED_NODE" ]] || {
    echo "Refusing to cordon a second node before restoring $CORDONED_NODE" >&2
    return 1
  }
  CORDONED_NODE="$(owner_node "$owner_id")"
  "${OC[@]}" adm cordon "$CORDONED_NODE" >/dev/null
}

restore_worker_spread() {
  restore_cordoned_node
  local deadline=$((SECONDS + 180))
  local ready distinct
  while (( SECONDS < deadline )); do
    read -r ready distinct < <("${OC[@]}" -n "$NAMESPACE" get pods \
      -l app.kubernetes.io/name=lifecycle-worker -o json \
      | jq -r '[.items[] | select(.status.containerStatuses[0].ready == true)] as $ready | [$ready|length, [$ready[].spec.nodeName]|unique|length] | @tsv')
    if [[ "$ready" == "2" && "$distinct" == "2" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "Lifecycle workers did not return to two Ready processes on distinct nodes" >&2
  return 1
}

delete_owner() {
  local owner_id="$1"
  local pod
  pod="$(owner_pod "$owner_id")"
  "${OC[@]}" -n "$NAMESPACE" delete pod "$pod" \
    --force --grace-period=0 --wait=false >/dev/null
  printf '%s' "$pod"
}

wait_for_takeover_completion() {
  local job_id="$1"
  local initial_fence="$2"
  local deleted_epoch="$3"
  local deadline=$((SECONDS + 1200))
  local row status fence takeover_epoch="" replacement_owner=""
  while (( SECONDS < deadline )); do
    row="$(job_json "$job_id")"
    status="$(jq -r '.status // empty' <<<"$row")"
    fence="$(jq -r '.fencing_token // 0' <<<"$row")"
    if (( fence > initial_fence )) && [[ -z "$takeover_epoch" ]]; then
      takeover_epoch="$(now_epoch)"
      replacement_owner="$(jq -r '.owner_id // empty' <<<"$row")"
    fi
    if [[ "$status" == "succeeded" ]]; then
      [[ -n "$takeover_epoch" ]] || {
        echo "Job $job_id succeeded without a higher fencing token" >&2
        return 1
      }
      jq -cn \
        --argjson final "$row" \
        --arg replacement_owner "$replacement_owner" \
        --argjson takeover_seconds "$(elapsed "$deleted_epoch" "$takeover_epoch")" \
        --argjson completion_seconds "$(elapsed "$deleted_epoch" "$(now_epoch)")" \
        '{final:$final,replacement_owner:$replacement_owner,takeover_seconds:$takeover_seconds,completion_seconds:$completion_seconds}'
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "Job $job_id failed after takeover: $(jq -r '.last_error // "unknown"' <<<"$row")" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "Timed out waiting for takeover of job $job_id" >&2
  return 1
}

wait_for_workshop_status() {
  local wanted="$1"
  local deadline=$((SECONDS + 1200))
  local workshop status
  while (( SECONDS < deadline )); do
    workshop="$(api GET "/api/v1/workshops/$WORKSHOP_ID")"
    status="$(jq -r '.status' <<<"$workshop")"
    if [[ "$status" == "$wanted" ]]; then
      printf '%s' "$workshop"
      return 0
    fi
    if [[ "$status" == "failed" || "$status" == "partially_ready" || "$status" == "preflight_failed" || "$status" == "completed_with_errors" ]]; then
      echo "Workshop $WORKSHOP_ID reached $status" >&2
      jq -c '{status,metadata,seats:[.seats[]|{seat_number,status,error}]}' <<<"$workshop" >&2
      return 1
    fi
    sleep 1
  done
  echo "Timed out waiting for workshop $WORKSHOP_ID to reach $wanted" >&2
  return 1
}

verify_ready_workshop() {
  local workshop="$1"
  jq -e --argjson seat_count "$SEAT_COUNT" '
    .status == "ready" and
    .cluster_ref == "arena" and
    .num_users == $seat_count and
    (.seats | length) == $seat_count and
    (.session_ids | length) == $seat_count and
    ([.seats[].status] | all(. == "ready")) and
    ([.seats[].session_id] | unique | length) == $seat_count and
    ([.seats[].seat_number] | unique | length) == $seat_count
  ' <<<"$workshop" >/dev/null || {
    echo "Ready workshop contract failed" >&2
    return 1
  }
}

showroom_http() {
  local url="$1"
  local deadline=$((SECONDS + 180))
  local code="000"
  while (( SECONDS < deadline )); do
    code="$(curl -ksS -o /dev/null -w '%{http_code}' --max-time 30 "$url" || true)"
    if [[ "$code" == "200" ]]; then
      printf '%s' "$code"
      return 0
    fi
    sleep 2
  done
  echo "Showroom $url returned HTTP $code" >&2
  return 1
}

verify_seat_sessions() {
  local workshop="$1"
  local seat seat_number seat_id session_id session status session_namespace
  local cluster_ref showroom_url http_code namespace_workshop namespace_session
  : >"$SEAT_PROOF_LINES"
  while IFS= read -r seat; do
    seat_number="$(jq -r '.seat_number' <<<"$seat")"
    seat_id="$(jq -r '.seat_id' <<<"$seat")"
    session_id="$(jq -r '.session_id' <<<"$seat")"
    session="$(api GET "/api/v1/lab-sessions/$session_id")"
    status="$(jq -r '.status' <<<"$session")"
    cluster_ref="$(jq -r '.cluster_ref' <<<"$session")"
    session_namespace="$(jq -r '.namespace' <<<"$session")"
    showroom_url="$(jq -r '.showroom_url // .lab_url // empty' <<<"$seat")"
    [[ "$status" == "ready" || "$status" == "active" ]] || {
      echo "Seat $seat_number session is $status" >&2
      return 1
    }
    [[ "$cluster_ref" == "arena" ]] || {
      echo "Seat $seat_number session was not persisted to Arena" >&2
      return 1
    }
    [[ -n "$session_namespace" && "$session_namespace" != "null" ]] || return 1
    [[ -n "$showroom_url" && "$showroom_url" != "null" ]] || return 1
    namespace_workshop="$("${OC[@]}" get namespace "$session_namespace" \
      -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/workshop-id}')"
    namespace_session="$("${OC[@]}" get namespace "$session_namespace" \
      -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/session-id}')"
    [[ "$namespace_workshop" == "$WORKSHOP_ID" ]] || {
      echo "Seat $seat_number namespace workshop label does not match" >&2
      return 1
    }
    [[ "$namespace_session" == "$session_id" ]] || {
      echo "Seat $seat_number namespace session label does not match" >&2
      return 1
    }
    http_code="$(showroom_http "$showroom_url")"
    jq -cn \
      --argjson seat_number "$seat_number" \
      --arg seat_id "$seat_id" \
      --arg session_id "$session_id" \
      --arg namespace "$session_namespace" \
      --arg showroom_url "$showroom_url" \
      --argjson showroom_http "$http_code" \
      --arg status "$status" \
      '{seat_number:$seat_number,seat_id:$seat_id,session_id:$session_id,namespace:$namespace,status:$status,showroom_url:$showroom_url,showroom_http:$showroom_http}' \
      >>"$SEAT_PROOF_LINES"
  done < <(jq -c '.seats | sort_by(.seat_number)[]' <<<"$workshop")

  local proofs unique_session_ids unique_namespaces
  proofs="$(jq -sc '.' "$SEAT_PROOF_LINES")"
  unique_session_ids="$(jq '[.[].session_id] | unique | length' <<<"$proofs")"
  unique_namespaces="$(jq '[.[].namespace] | unique | length' <<<"$proofs")"
  [[ "$(jq 'length' <<<"$proofs")" == "$SEAT_COUNT" \
    && "$unique_session_ids" == "$SEAT_COUNT" \
    && "$unique_namespaces" == "$SEAT_COUNT" ]] || {
    echo "Workshop did not produce $SEAT_COUNT unique session and namespace assignments" >&2
    return 1
  }
  printf '%s' "$proofs"
}

workshop_residue() {
  local selector="$WORKSHOP_ID_LABEL=$WORKSHOP_ID"
  local namespaces routes rolebindings applications
  namespaces="$("${OC[@]}" get namespaces -l "$selector" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  routes="$("${OC[@]}" get routes -A -l "$selector" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  rolebindings="$("${OC[@]}" get rolebindings -A -l "$selector" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  applications="$("${OC[@]}" get applications.argoproj.io -A -l "$selector" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  printf '%s|%s|%s|%s' "$namespaces" "$routes" "$rolebindings" "$applications"
}

wait_for_zero_workshop_residue() {
  local deadline=$((SECONDS + 600))
  local counts
  while (( SECONDS < deadline )); do
    counts="$(workshop_residue)"
    if [[ "$counts" == "0|0|0|0" ]]; then
      printf '%s' "$counts"
      return 0
    fi
    sleep 1
  done
  echo "Cleanup residue remains for workshop $WORKSHOP_ID: $counts" >&2
  return 1
}

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked repository files must be committed before certification" >&2
  exit 1
fi

SERVER="$("${OC[@]}" whoami --show-server)"
[[ "$SERVER" == "https://api.arena.fm2aihpcsed.com:6443" ]] || {
  echo "Kubeconfig targets $SERVER, not Arena" >&2
  exit 1
}

READY_NODES="$("${OC[@]}" get nodes -l node-role.kubernetes.io/worker \
  -o json | jq '[.items[] | select(.status.conditions[] | .type == "Ready" and .status == "True") | select(.spec.unschedulable != true)] | length')"
[[ "$READY_NODES" -ge 2 ]] || {
  echo "Workshop HA requires two Ready schedulable worker nodes" >&2
  exit 1
}
WORKER_STATE="$("${OC[@]}" -n "$NAMESPACE" get pods \
  -l app.kubernetes.io/name=lifecycle-worker -o json)"
READY_WORKERS="$(jq '[.items[] | select(.status.containerStatuses[0].ready == true)] | length' <<<"$WORKER_STATE")"
DISTINCT_WORKER_NODES="$(jq '[.items[] | select(.status.containerStatuses[0].ready == true) | .spec.nodeName] | unique | length' <<<"$WORKER_STATE")"
[[ "$READY_WORKERS" == "2" ]] || {
  echo "Exactly two lifecycle worker processes must be ready" >&2
  exit 1
}
[[ "$DISTINCT_WORKER_NODES" == "2" ]] || {
  echo "Workshop HA requires two distinct worker nodes" >&2
  exit 1
}
[[ "$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker \
  -o jsonpath='{.spec.template.spec.topologySpreadConstraints[0].whenUnsatisfiable}')" == "DoNotSchedule" ]] || {
  echo "Workshop HA requires hard topology spreading" >&2
  exit 1
}
[[ "$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker \
  -o jsonpath='{.spec.template.spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].topologyKey}')" == "kubernetes.io/hostname" ]] || {
  echo "Workshop HA requires hostname pod anti-affinity" >&2
  exit 1
}
[[ "$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker \
  -o jsonpath='{.spec.strategy.rollingUpdate.maxUnavailable}')" == "1" \
  && "$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker \
  -o jsonpath='{.spec.strategy.rollingUpdate.maxSurge}')" == "0" ]] || {
  echo "Workshop HA requires a no-surge one-at-a-time rollout" >&2
  exit 1
}
[[ "$("${OC[@]}" -n "$NAMESPACE" get configmap launchpad-config -o jsonpath='{.data.LIFECYCLE_HA_ENABLED}')" == "true" ]] || {
  echo "Lifecycle HA is not enabled" >&2
  exit 1
}
[[ "$("${OC[@]}" -n "$NAMESPACE" get configmap launchpad-config -o jsonpath='{.data.LAUNCHPAD_CONTROL_PLANE_ROLE}')" == "active" ]] || {
  echo "Arena is not the active control plane" >&2
  exit 1
}
[[ "$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LIFECYCLE_JOB_LEASE_SECONDS")].value}')" == "30" ]] || {
  echo "The certified 30-second worker lease is not deployed" >&2
  exit 1
}

"${OC[@]}" get namespace "$PUBLIC_CERT_NAMESPACE" >/dev/null
ADMIN_KEY_B64="$("${OC[@]}" -n "$NAMESPACE" get secret launchpad-api-keys -o jsonpath='{.data.admin}')"
ADMIN_KEY="$(printf '%s' "$ADMIN_KEY_B64" | base64 -d)"
ADMIN_KEY_B64=""
"${OC[@]}" -n "$NAMESPACE" port-forward service/backend "$LOCAL_PORT:8000" >"$PF_LOG" 2>&1 &
PF_PID=$!
for _ in {1..30}; do
  if curl -fsS "$API_BASE/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
[[ "$(curl -fsS "$API_BASE/ready" | jq -r '.status')" == "ready" ]] || {
  echo "Backend readiness failed" >&2
  exit 1
}

REQUEST_BODY="$(jq -cn \
  --arg tenant "$TENANT_ID" \
  --arg catalog "$CATALOG_ITEM_ID" \
  --arg owner "$OWNER_ID" \
  --argjson seat_count "$SEAT_COUNT" \
  '{"tenant_id":$tenant,"catalog_item_id":$catalog,"num_users":$seat_count,"owner_id":$owner,"ttl":"2h","purpose":"certification","target_cluster":"arena","exposure_policy":"internal"}')"
CAPACITY="$(api POST /api/v1/workshops/capacity-preview "$REQUEST_BODY")"
[[ "$(jq -r '.can_provision' <<<"$CAPACITY")" == "true" \
  && "$(jq -r '.selected_cluster' <<<"$CAPACITY")" == "arena" ]] || {
  echo "Arena capacity preview rejected $SEAT_COUNT seats: $(jq -r '.reason' <<<"$CAPACITY")" >&2
  exit 1
}

IDEMPOTENCY_KEY="arena-workshop-ha-${SEAT_COUNT}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
ORDER="$(api_idempotent_post /api/v1/workshops/orders "$IDEMPOTENCY_KEY" "$REQUEST_BODY")"
WORKSHOP_ID="$(jq -r '.workshop_id' <<<"$ORDER")"
[[ "$(jq -r '.cluster_ref' <<<"$ORDER")" == "arena" ]] || {
  echo "Workshop order did not persist Arena" >&2
  exit 1
}
CONFIRMED="$(api POST "/api/v1/workshops/$WORKSHOP_ID/confirm")"
PROVISION_JOB_ID="$(jq -r '.metadata.lifecycle_job_id' <<<"$CONFIRMED")"

PROVISION_INITIAL="$(wait_for_claim "$PROVISION_JOB_ID" provision_workshop)"
PROVISION_INITIAL_FENCE="$(jq -r '.fencing_token' <<<"$PROVISION_INITIAL")"
PROVISION_INITIAL_OWNER="$(jq -r '.owner_id' <<<"$PROVISION_INITIAL")"
PROVISION_INITIAL_NODE="$(owner_node "$PROVISION_INITIAL_OWNER")"
cordon_owner_node "$PROVISION_INITIAL_OWNER"
PROVISION_DELETED_EPOCH="$(now_epoch)"
PROVISION_DELETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PROVISION_DELETED_POD="$(delete_owner "$PROVISION_INITIAL_OWNER")"
PROVISION_TAKEOVER="$(wait_for_takeover_completion "$PROVISION_JOB_ID" "$PROVISION_INITIAL_FENCE" "$PROVISION_DELETED_EPOCH")"
READY_WORKSHOP="$(wait_for_workshop_status ready)"
verify_ready_workshop "$READY_WORKSHOP"
restore_worker_spread
SEAT_PROOFS="$(verify_seat_sessions "$READY_WORKSHOP")"

hold_showroom_applications "$SEAT_PROOFS"
RECLAIM_RESPONSE="$(api DELETE "/api/v1/workshops/$WORKSHOP_ID")"
RECLAIM_JOB_ID="$(jq -r '.metadata.lifecycle_job_id' <<<"$RECLAIM_RESPONSE")"
RECLAIM_INITIAL="$(wait_for_claim "$RECLAIM_JOB_ID" reclaim_workshop)"
RECLAIM_INITIAL_FENCE="$(jq -r '.fencing_token' <<<"$RECLAIM_INITIAL")"
RECLAIM_INITIAL_OWNER="$(jq -r '.owner_id' <<<"$RECLAIM_INITIAL")"
RECLAIM_INITIAL_NODE="$(owner_node "$RECLAIM_INITIAL_OWNER")"
cordon_owner_node "$RECLAIM_INITIAL_OWNER"
RECLAIM_DELETED_EPOCH="$(now_epoch)"
RECLAIM_DELETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RECLAIM_DELETED_POD="$(delete_owner "$RECLAIM_INITIAL_OWNER")"
# Hold every test Application until the dead owner's lease has expired so the
# aggregate reclaim cannot finish before the replacement proves takeover.
sleep 31
release_showroom_application_holds
RECLAIM_TAKEOVER="$(wait_for_takeover_completion "$RECLAIM_JOB_ID" "$RECLAIM_INITIAL_FENCE" "$RECLAIM_DELETED_EPOCH")"
COMPLETED_WORKSHOP="$(wait_for_workshop_status completed)"
[[ "$(jq '[.seats[] | select(.status == "reclaimed")] | length' <<<"$COMPLETED_WORKSHOP")" == "$SEAT_COUNT" ]] || {
  echo "Not every workshop seat reached reclaimed" >&2
  exit 1
}
RECLAIM_COMPLETED="true"
restore_worker_spread

RESIDUE="$(wait_for_zero_workshop_residue)"
IFS='|' read -r NAMESPACE_RESIDUE ROUTE_RESIDUE ROLEBINDING_RESIDUE APPLICATION_RESIDUE <<<"$RESIDUE"
"${OC[@]}" get namespace "$PUBLIC_CERT_NAMESPACE" >/dev/null

WORKER_NODES="$("${OC[@]}" -n "$NAMESPACE" get pods \
  -l app.kubernetes.io/name=lifecycle-worker -o json \
  | jq -c '[.items[] | select(.status.containerStatuses[0].ready == true) | .spec.nodeName] | unique')"
IMAGE="$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker \
  -o jsonpath='{.spec.template.spec.containers[0].image}')"
COMMIT="$(git rev-parse HEAD)"
if [[ "$SEAT_COUNT" == "5" ]]; then
  RESULT="GREEN-live-five-seat-cross-node-workshop-ha"
else
  RESULT="GREEN-live-twenty-five-seat-cross-node-workshop-ha"
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
jq -n \
  --arg evidence_id "ARENA-LIFECYCLE-${SEAT_COUNT}-SEAT-CROSS-NODE-WORKSHOP-HA-$(date -u +%Y%m%dT%H%M%SZ)" \
  --arg result "$RESULT" \
  --arg commit "$COMMIT" \
  --arg image "$IMAGE" \
  --arg workshop_id "$WORKSHOP_ID" \
  --arg catalog_item_id "$CATALOG_ITEM_ID" \
  --argjson seat_count "$SEAT_COUNT" \
  --arg provision_job_id "$PROVISION_JOB_ID" \
  --arg provision_deleted_pod "$PROVISION_DELETED_POD" \
  --arg provision_deleted_at "$PROVISION_DELETED_AT" \
  --arg provision_initial_node "$PROVISION_INITIAL_NODE" \
  --argjson provision_initial "$PROVISION_INITIAL" \
  --argjson provision_takeover "$PROVISION_TAKEOVER" \
  --arg reclaim_job_id "$RECLAIM_JOB_ID" \
  --arg reclaim_deleted_pod "$RECLAIM_DELETED_POD" \
  --arg reclaim_deleted_at "$RECLAIM_DELETED_AT" \
  --arg reclaim_initial_node "$RECLAIM_INITIAL_NODE" \
  --argjson reclaim_initial "$RECLAIM_INITIAL" \
  --argjson reclaim_takeover "$RECLAIM_TAKEOVER" \
  --argjson worker_nodes "$WORKER_NODES" \
  --argjson seat_proofs "$SEAT_PROOFS" \
  --argjson namespace_residue "$NAMESPACE_RESIDUE" \
  --argjson route_residue "$ROUTE_RESIDUE" \
  --argjson rolebinding_residue "$ROLEBINDING_RESIDUE" \
  --argjson application_residue "$APPLICATION_RESIDUE" \
  '{
    schema:"launchpad.redhat.com/workshop-lifecycle-ha-live-certification/v1",
    evidence_id:$evidence_id,
    result:$result,
    source:{commit:$commit,backend_image:$image,cluster_ref:"arena"},
    topology:{worker_processes:2,worker_nodes:$worker_nodes,node_separated_processes:true,node_ha_certified:false},
    workshop:{workshop_id:$workshop_id,catalog_item_id:$catalog_item_id,cluster_ref:"arena",seats_requested:$seat_count,seats_ready:$seat_count,unique_session_ids:([$seat_proofs[].session_id]|unique|length),unique_namespaces:([$seat_proofs[].namespace]|unique|length),seat_proofs:$seat_proofs},
    provision_takeover:{job_id:$provision_job_id,operation:"PROVISION_WORKSHOP",initial_owner_node:$provision_initial_node,deleted_pod:$provision_deleted_pod,deleted_at:$provision_deleted_at,initial:$provision_initial,takeover:$provision_takeover},
    reclaim_takeover:{job_id:$reclaim_job_id,operation:"RECLAIM_WORKSHOP",initial_owner_node:$reclaim_initial_node,deleted_pod:$reclaim_deleted_pod,deleted_at:$reclaim_deleted_at,initial:$reclaim_initial,takeover:$reclaim_takeover},
    cleanup:{namespaces:$namespace_residue,routes:$route_residue,role_bindings:$rolebinding_residue,argocd_applications:$application_residue},
    public_certification_lab_preserved:true,
    proof_strategy:{TDD:"Certifier safety, seat uniqueness and evidence contracts were RED before implementation.",EDD:"The receipt records immutable source, aggregate jobs, fences, timings, every seat route and aggregate cleanup counts.",CDD:"Workshop, session, placement, lifecycle-job and resource-label contracts are checked.",BDD:"A workshop must survive aggregate provision and reclaim owner loss with every seat usable and zero residue.",CBT:"Queue ownership, placement, sessions, namespaces, Showroom routes, Applications and cleanup are checked independently."},
    certification_boundary:{five_seat_workshop_process_ha:(if $seat_count == 5 then "certified" else "inherited" end),twenty_five_seat_workshop_ha:(if $seat_count == 25 then "certified" else "not certified" end),hard_node_failure:"not certified",flightpath_dr:"not certified"},
    security:{contains_plaintext_credentials:false,credential_values_logged:false}
  }' >"$OUTPUT_PATH"
shasum -a 256 "$OUTPUT_PATH" >"$OUTPUT_PATH.sha256"

echo "Arena $SEAT_COUNT-seat cross-node workshop process-HA certification ($RESULT): GREEN"
echo "Evidence: $OUTPUT_PATH"
echo "Checksum: $OUTPUT_PATH.sha256"
