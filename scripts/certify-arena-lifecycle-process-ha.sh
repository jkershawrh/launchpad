#!/usr/bin/env bash
set -euo pipefail

# Deterministic one-seat lifecycle process-takeover proof for Arena.
#
# This intentionally deletes the lifecycle worker that owns each test job. In
# cross-node mode it also cordons only the owning node, then always restores it;
# it never drains or reboots a node. Tenant-resource cleanup remains scoped to
# the generated session.

usage() {
  echo "usage: $0 /absolute/arena.kubeconfig --confirm-worker-deletion [--cross-node]" >&2
  exit 2
}

[[ $# -eq 2 || $# -eq 3 ]] || usage
KUBECONFIG_PATH="$1"
[[ "$2" == "--confirm-worker-deletion" ]] || usage
CROSS_NODE="false"
if [[ $# -eq 3 ]]; then
  [[ "$3" == "--cross-node" ]] || usage
  CROSS_NODE="true"
fi
[[ "$KUBECONFIG_PATH" == /* && -f "$KUBECONFIG_PATH" ]] || {
  echo "Arena kubeconfig must be an explicit absolute file" >&2
  exit 2
}

NAMESPACE="partner-ai-launchpad"
TENANT_ID="${TENANT_ID:-ha-cert-tenant}"
CATALOG_ITEM_ID="${CATALOG_ITEM_ID:-intel-llm-cpu-serving}"
REQUESTER_ID="${REQUESTER_ID:-arena-process-ha-certifier}"
LOCAL_PORT="${LOCAL_PORT:-18102}"
API_BASE="http://127.0.0.1:${LOCAL_PORT}"
if [[ "$CROSS_NODE" == "true" ]]; then
  DEFAULT_OUTPUT_PATH="evidence/runs/arena-lifecycle-cross-node-process-ha-$(date -u +%Y%m%dT%H%M%SZ).json"
else
  DEFAULT_OUTPUT_PATH="evidence/runs/arena-lifecycle-process-ha-clean-$(date -u +%Y%m%dT%H%M%SZ).json"
fi
OUTPUT_PATH="${OUTPUT_PATH:-$DEFAULT_OUTPUT_PATH}"

OC=(oc --kubeconfig "$KUBECONFIG_PATH")
PF_PID=""
CERT_TMP="$(mktemp -d)"
PF_LOG="$CERT_TMP/backend-port-forward.log"
SESSION_ID=""
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

queue_reclaim_best_effort() {
  if [[ -n "$SESSION_ID" && "$RECLAIM_COMPLETED" != "true" && -n "$PF_PID" ]]; then
    api POST "/api/v1/lab-sessions/$SESSION_ID/reclaim" >/dev/null 2>&1 || true
  fi
}

restore_cordoned_node() {
  if [[ -n "$CORDONED_NODE" ]]; then
    "${OC[@]}" adm uncordon "$CORDONED_NODE" >/dev/null
    CORDONED_NODE=""
  fi
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  restore_cordoned_node >/dev/null 2>&1 || true
  queue_reclaim_best_effort
  if [[ -n "$PF_PID" ]]; then
    kill "$PF_PID" >/dev/null 2>&1 || true
    wait "$PF_PID" >/dev/null 2>&1 || true
  fi
  ADMIN_KEY=""
  if [[ "$CERT_TMP" == /tmp/* || "$CERT_TMP" == /var/folders/* ]]; then
    rm -f "$PF_LOG"
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
    "SELECT json_build_object('status', status, 'owner_id', owner_id, 'fencing_token', fencing_token, 'attempts', attempts, 'step', step, 'last_error', last_error)::text FROM lifecycle_jobs WHERE job_id = '$job_id';"
}

wait_for_claim() {
  local job_id="$1"
  local deadline=$((SECONDS + 45))
  local row status owner
  while (( SECONDS < deadline )); do
    row="$(job_json "$job_id")"
    status="$(jq -r '.status // empty' <<<"$row")"
    owner="$(jq -r '.owner_id // empty' <<<"$row")"
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
  [[ "$CROSS_NODE" == "true" ]] || return 0
  [[ -z "$CORDONED_NODE" ]] || {
    echo "Refusing to cordon a second node before restoring $CORDONED_NODE" >&2
    return 1
  }
  CORDONED_NODE="$(owner_node "$owner_id")"
  "${OC[@]}" adm cordon "$CORDONED_NODE" >/dev/null
}

restore_worker_spread() {
  [[ "$CROSS_NODE" == "true" ]] || return 0
  restore_cordoned_node
  local distinct pod deadline
  distinct="$("${OC[@]}" -n "$NAMESPACE" get pods \
    -l app.kubernetes.io/name=lifecycle-worker -o json \
    | jq '[.items[].spec.nodeName] | unique | length')"
  if [[ "$distinct" != "2" ]]; then
    pod="$("${OC[@]}" -n "$NAMESPACE" get pods \
      -l app.kubernetes.io/name=lifecycle-worker \
      --sort-by=.metadata.creationTimestamp \
      -o jsonpath='{.items[-1].metadata.name}')"
    "${OC[@]}" -n "$NAMESPACE" delete pod "$pod" --wait=false >/dev/null
  fi
  deadline=$((SECONDS + 120))
  while (( SECONDS < deadline )); do
    distinct="$("${OC[@]}" -n "$NAMESPACE" get pods \
      -l app.kubernetes.io/name=lifecycle-worker -o json \
      | jq '[.items[] | select(.status.containerStatuses[0].ready == true) | .spec.nodeName] | unique | length')"
    if [[ "$distinct" == "2" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "Lifecycle workers did not return to two distinct nodes" >&2
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
  local deadline=$((SECONDS + 300))
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

wait_for_session_status() {
  local wanted="$1"
  local deadline=$((SECONDS + 300))
  local session status
  while (( SECONDS < deadline )); do
    session="$(api GET "/api/v1/lab-sessions/$SESSION_ID")"
    status="$(jq -r '.status' <<<"$session")"
    if [[ "$status" == "$wanted" ]]; then
      printf '%s' "$session"
      return 0
    fi
    if [[ "$status" == "failed" || "$status" == "cleanup_failed" || "$status" == "validation_failed" ]]; then
      echo "Session $SESSION_ID reached $status" >&2
      return 1
    fi
    sleep 1
  done
  echo "Timed out waiting for session $SESSION_ID to reach $wanted" >&2
  return 1
}

resource_residue() {
  local session_namespace="$1"
  local session_id="$2"
  local namespaces=0
  local routes role_bindings applications
  if "${OC[@]}" get namespace "$session_namespace" >/dev/null 2>&1; then
    namespaces=1
  fi
  routes="$("${OC[@]}" get routes -A -l "launchpad.redhat.com/session-id=$session_id" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  role_bindings="$("${OC[@]}" get rolebindings -A -l "launchpad.redhat.com/session-id=$session_id" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  applications="$("${OC[@]}" get applications.argoproj.io -A -l "launchpad.redhat.com/session-id=$session_id" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  printf '%s|%s|%s|%s' "$namespaces" "$routes" "$role_bindings" "$applications"
}

wait_for_zero_residue() {
  local session_namespace="$1"
  local session_id="$2"
  local deadline=$((SECONDS + 180))
  local counts
  while (( SECONDS < deadline )); do
    counts="$(resource_residue "$session_namespace" "$session_id")"
    if [[ "$counts" == "0|0|0|0" ]]; then
      printf '%s' "$counts"
      return 0
    fi
    sleep 1
  done
  echo "Cleanup residue remains for session $session_id: $counts" >&2
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

if [[ "$CROSS_NODE" == "true" ]]; then
  [[ "$("${OC[@]}" get node rhgnr1 -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" == "True" ]] || {
    echo "rhgnr1 must be Ready for cross-node mode" >&2
    exit 1
  }
  [[ -z "$("${OC[@]}" get node rhgnr1 -o jsonpath='{.spec.unschedulable}')" ]] || {
    echo "rhgnr1 must be schedulable for cross-node mode" >&2
    exit 1
  }
  DISTINCT_WORKER_NODES="$("${OC[@]}" -n "$NAMESPACE" get pods \
    -l app.kubernetes.io/name=lifecycle-worker -o json \
    | jq '[.items[] | select(.status.containerStatuses[0].ready == true) | .spec.nodeName] | unique | length')"
  [[ "$DISTINCT_WORKER_NODES" == "2" ]] || {
    echo "Cross-node mode requires two distinct worker nodes" >&2
    exit 1
  }
else
  [[ "$("${OC[@]}" get node rhgnr1 -o jsonpath='{.spec.unschedulable}')" == "true" ]] || {
    echo "rhgnr1 must remain cordoned while Intel investigates it" >&2
    exit 1
  }
fi
[[ "$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker -o jsonpath='{.status.readyReplicas}')" == "2" ]] || {
  echo "Exactly two lifecycle worker processes must be ready" >&2
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
[[ "$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LIFECYCLE_JOB_LEASE_SECONDS")].value}')" == "30" ]] || {
  echo "The certified 30-second worker lease is not deployed" >&2
  exit 1
}

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

READY="$(curl -fsS "$API_BASE/ready")"
[[ "$(jq -r '.status' <<<"$READY")" == "ready" ]] || {
  echo "Backend readiness failed" >&2
  exit 1
}

PUBLIC_CERT_NAMESPACE="launchpad-public-cert-tenant-intel-llm-cpu-serv-205782"
"${OC[@]}" get namespace "$PUBLIC_CERT_NAMESPACE" >/dev/null

REQUEST_BODY="$(jq -cn \
  --arg tenant "$TENANT_ID" \
  --arg requester "$REQUESTER_ID" \
  --arg catalog "$CATALOG_ITEM_ID" \
  --arg certification "$(if [[ "$CROSS_NODE" == "true" ]]; then echo lifecycle-cross-node-process-ha; else echo lifecycle-process-ha-clean; fi)" \
  '{tenant_id:$tenant,requester_id:$requester,catalog_item_id:$catalog,requested_mode:"guided_build",persistence:"ephemeral",ttl:"2h",hardware_profile:"xeon-basic",quota_profile:"small",exposure_policy:"internal",metadata:{target_cluster:"arena",certification:$certification}}')"
REQUEST="$(api POST /api/v1/lab-requests "$REQUEST_BODY")"
[[ "$(jq -r '.status' <<<"$REQUEST")" == "accepted" ]] || {
  echo "Certification request was not accepted" >&2
  exit 1
}
REQUEST_ID="$(jq -r '.request_id' <<<"$REQUEST")"

PROVISION_RESPONSE="$(api POST "/api/v1/lab-requests/$REQUEST_ID/provision")"
SESSION_ID="$(jq -r '.session_id' <<<"$PROVISION_RESPONSE")"
PROVISION_JOB_ID="$(jq -r '.metadata.lifecycle_job_id' <<<"$PROVISION_RESPONSE")"
[[ "$(jq -r '.cluster_ref' <<<"$PROVISION_RESPONSE")" == "arena" ]] || {
  echo "Provisioning did not persist Arena" >&2
  exit 1
}

PROVISION_INITIAL="$(wait_for_claim "$PROVISION_JOB_ID")"
PROVISION_INITIAL_FENCE="$(jq -r '.fencing_token' <<<"$PROVISION_INITIAL")"
PROVISION_INITIAL_OWNER="$(jq -r '.owner_id' <<<"$PROVISION_INITIAL")"
PROVISION_INITIAL_NODE="$(owner_node "$PROVISION_INITIAL_OWNER")"
cordon_owner_node "$PROVISION_INITIAL_OWNER"
PROVISION_DELETED_EPOCH="$(now_epoch)"
PROVISION_DELETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PROVISION_DELETED_POD="$(delete_owner "$PROVISION_INITIAL_OWNER")"
PROVISION_TAKEOVER="$(wait_for_takeover_completion "$PROVISION_JOB_ID" "$PROVISION_INITIAL_FENCE" "$PROVISION_DELETED_EPOCH")"
READY_SESSION="$(wait_for_session_status ready)"
restore_worker_spread
SESSION_NAMESPACE="$(jq -r '.namespace' <<<"$READY_SESSION")"
LAB_URL="$(jq -r '.lab_url' <<<"$READY_SESSION")"
[[ -n "$SESSION_NAMESPACE" && "$SESSION_NAMESPACE" != "null" ]] || exit 1
[[ "$("${OC[@]}" get namespace "$SESSION_NAMESPACE" -o jsonpath='{.metadata.labels.launchpad\.redhat\.com/session-id}')" == "$SESSION_ID" ]] || {
  echo "Session namespace label does not match" >&2
  exit 1
}
SHOWROOM_HTTP="$(curl -ksS -o /dev/null -w '%{http_code}' --max-time 30 "$LAB_URL")"
[[ "$SHOWROOM_HTTP" == "200" ]] || {
  echo "Showroom returned HTTP $SHOWROOM_HTTP" >&2
  exit 1
}

RECLAIM_RESPONSE="$(api POST "/api/v1/lab-sessions/$SESSION_ID/reclaim")"
RECLAIM_JOB_ID="$(jq -r '.metadata.lifecycle_job_id' <<<"$RECLAIM_RESPONSE")"
RECLAIM_INITIAL="$(wait_for_claim "$RECLAIM_JOB_ID")"
RECLAIM_INITIAL_FENCE="$(jq -r '.fencing_token' <<<"$RECLAIM_INITIAL")"
RECLAIM_INITIAL_OWNER="$(jq -r '.owner_id' <<<"$RECLAIM_INITIAL")"
RECLAIM_INITIAL_NODE="$(owner_node "$RECLAIM_INITIAL_OWNER")"
cordon_owner_node "$RECLAIM_INITIAL_OWNER"
RECLAIM_DELETED_EPOCH="$(now_epoch)"
RECLAIM_DELETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RECLAIM_DELETED_POD="$(delete_owner "$RECLAIM_INITIAL_OWNER")"
RECLAIM_TAKEOVER="$(wait_for_takeover_completion "$RECLAIM_JOB_ID" "$RECLAIM_INITIAL_FENCE" "$RECLAIM_DELETED_EPOCH")"
RECLAIMED_SESSION="$(wait_for_session_status reclaimed)"
RECLAIM_COMPLETED="true"
restore_worker_spread

RESIDUE="$(wait_for_zero_residue "$SESSION_NAMESPACE" "$SESSION_ID")"
IFS='|' read -r NAMESPACE_RESIDUE ROUTE_RESIDUE ROLEBINDING_RESIDUE APPLICATION_RESIDUE <<<"$RESIDUE"
"${OC[@]}" get namespace "$PUBLIC_CERT_NAMESPACE" >/dev/null

WORKER_NODES="$("${OC[@]}" -n "$NAMESPACE" get pods -l app.kubernetes.io/name=lifecycle-worker -o json | jq -c '[.items[].spec.nodeName] | unique')"
IMAGE="$("${OC[@]}" -n "$NAMESPACE" get deployment lifecycle-worker -o jsonpath='{.spec.template.spec.containers[0].image}')"
COMMIT="$(git rev-parse HEAD)"
if [[ "$CROSS_NODE" == "true" ]]; then
  EVIDENCE_ID_PREFIX="ARENA-LIFECYCLE-CROSS-NODE-PROCESS-HA"
  RESULT="GREEN-live-cross-node-process-ha"
else
  EVIDENCE_ID_PREFIX="ARENA-LIFECYCLE-PROCESS-HA-CLEAN"
  RESULT="GREEN-live-clean-process-ha"
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
jq -n \
  --arg evidence_id "$EVIDENCE_ID_PREFIX-$(date -u +%Y%m%dT%H%M%SZ)" \
  --arg result "$RESULT" \
  --argjson cross_node "$CROSS_NODE" \
  --arg commit "$COMMIT" \
  --arg image "$IMAGE" \
  --arg request_id "$REQUEST_ID" \
  --arg session_id "$SESSION_ID" \
  --arg namespace "$SESSION_NAMESPACE" \
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
  --argjson namespace_residue "$NAMESPACE_RESIDUE" \
  --argjson route_residue "$ROUTE_RESIDUE" \
  --argjson rolebinding_residue "$ROLEBINDING_RESIDUE" \
  --argjson application_residue "$APPLICATION_RESIDUE" \
  --arg showroom_http "$SHOWROOM_HTTP" \
  '{
    schema:"launchpad.redhat.com/lifecycle-ha-live-certification/v1",
    evidence_id:$evidence_id,
    result:$result,
    source:{commit:$commit,backend_image:$image,cluster_ref:"arena"},
    topology:{worker_processes:2,worker_nodes:$worker_nodes,rhgnr1_cordoned:($cross_node | not),node_separated_processes:$cross_node,node_ha_certified:false},
    order:{request_id:$request_id,session_id:$session_id,namespace:$namespace,cluster_ref:"arena",showroom_http:($showroom_http|tonumber)},
    provision_takeover:{job_id:$provision_job_id,initial_owner_node:$provision_initial_node,deleted_pod:$provision_deleted_pod,deleted_at:$provision_deleted_at,initial:$provision_initial,takeover:$provision_takeover},
    reclaim_takeover:{job_id:$reclaim_job_id,initial_owner_node:$reclaim_initial_node,deleted_pod:$reclaim_deleted_pod,deleted_at:$reclaim_deleted_at,initial:$reclaim_initial,takeover:$reclaim_takeover},
    cleanup:{namespaces:$namespace_residue,routes:$route_residue,role_bindings:$rolebinding_residue,argocd_applications:$application_residue},
    public_certification_lab_preserved:true,
    proof_strategy:{TDD:"Certifier safety and evidence contracts are tested before the live run.",EDD:"The receipt records immutable source, job IDs, fences, timings, route status and cleanup counts.",CDD:"Persisted session, queue, cluster target and resource-label contracts are checked.",BDD:"Deleting each owning process must produce a higher fence, successful completion and zero cleanup residue.",CBT:"Readiness, queue ownership, Showroom, session state and resource cleanup are checked independently."},
    certification_boundary:{process_ha:"certified",hard_node_failure:"not certified",node_ha:"not certified",workshop_ha:"not certified",flightpath_dr:"not certified"} + (if $cross_node then {cross_node_process_ha:"certified"} else {cross_node_process_ha:"not certified"} end),
    security:{contains_plaintext_credentials:false,credential_values_logged:false}
  }' >"$OUTPUT_PATH"
shasum -a 256 "$OUTPUT_PATH" >"$OUTPUT_PATH.sha256"

echo "Arena lifecycle process-HA certification ($RESULT): GREEN"
echo "Evidence: $OUTPUT_PATH"
echo "Checksum: $OUTPUT_PATH.sha256"
