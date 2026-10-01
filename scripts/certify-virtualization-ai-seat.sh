#!/usr/bin/env bash
set -euo pipefail

catalog_id="${1:?usage: certify-virtualization-ai-seat.sh <catalog-id> <namespace> <cluster-id>}"
namespace="${2:?usage: certify-virtualization-ai-seat.sh <catalog-id> <namespace> <cluster-id>}"
expected_cluster="${3:?usage: certify-virtualization-ai-seat.sh <catalog-id> <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

stage=setup
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
probe_binding=launchpad-certification-probe
probe_serviceaccount="${LAUNCHPAD_CERTIFICATION_SERVICEACCOUNT:-launchpad-flightpath-candidate:launchpad-certification-runner}"
work_dir="$(mktemp -d)"
forward_pid=""
forward_port="${LAUNCHPAD_CERTIFICATION_FORWARD_PORT:-18080}"
source_revision=""
expected_presentation_image=""
expected_adapter_image=""

cleanup() {
  [[ -z "$forward_pid" ]] || kill "$forward_pid" >/dev/null 2>&1 || true
  oc --kubeconfig "$KUBECONFIG" delete rolebinding "$probe_binding" -n "$namespace" --ignore-not-found >/dev/null 2>&1 || true
  rm -rf "$work_dir"
}
trap cleanup EXIT

wait_for_resource() {
  local kind="$1"
  local name="$2"
  for _ in {1..120}; do
    oc --kubeconfig "$KUBECONFIG" get "$kind/$name" -n "$namespace" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

oc --kubeconfig "$KUBECONFIG" create rolebinding "$probe_binding" --clusterrole=edit \
  --serviceaccount="$probe_serviceaccount" -n "$namespace" --dry-run=client -o yaml \
  | oc --kubeconfig "$KUBECONFIG" apply -f - >/dev/null

case "$catalog_id" in
  virtualization-ai-foundations-101)
    vm_names=(operations-vm); service=ai-analysis; route=lab; endpoint=/api/v1/analyze
    source_revision="e74393d0def1a7a2749911b3a421c62f3f1c2558"
    expected_presentation_image="ghcr.io/jkershawrh/virtualization-ai-foundations-presentation@sha256:c0e16f6c63a59989f0da349a97a8e661cb5eca3e356e1664ff571979551f50f0"
    expected_adapter_image="ghcr.io/jkershawrh/virtualization-ai-foundations-adapter@sha256:fef33f72569296df84888102c0dab19b607b56a14a5516de7eed1279dbb3fbad" ;;
  virtualization-ai-201)
    vm_names=(contract-author-vm); service=virtualization-ai-201-adapter; route=lab; endpoint=/api/v1/qualify
    source_revision="3c94600ca8808a55693e94d5a1f169efbadbedd1"
    expected_presentation_image="ghcr.io/jkershawrh/virtualization-ai-201-presentation@sha256:2749e4ad44f3902f7507adaaaa8fadd509d1e625b33619530852bd9a01255069"
    expected_adapter_image="ghcr.io/jkershawrh/virtualization-ai-201-adapter@sha256:99f1ac6f65386013cb20d81e3dbc6099ffbb63cebfdc6fb1f1cdd50d96153a39" ;;
  virtualization-ai-301)
    vm_names=(modernization-client); service=virtualization-ai-301-adapter; route=virt301; endpoint=/api/v1/modernize ;;
  virtualization-ai-401)
    vm_names=(operations-client); service=virtualization-ai-401-operations-adapter; route=virtualization-ai-401; endpoint=/api/v1/operations ;;
  virtualization-ai-501)
    vm_names=(inference-client-a inference-client-b inference-client-c); service=virtualization-ai-501-qualification-adapter; route=virtualization-ai-501; endpoint=/api/v1/qualifications ;;
  *) printf 'unsupported catalog: %s\n' "$catalog_id" >&2; exit 2 ;;
esac

stage=vm-ready
for vm in "${vm_names[@]}"; do
  wait_for_resource vm "$vm"
  oc --kubeconfig "$KUBECONFIG" wait -n "$namespace" --for=jsonpath='{.status.printableStatus}'=Running "vm/$vm" --timeout=600s >/dev/null
  wait_for_resource vmi "$vm"
  oc --kubeconfig "$KUBECONFIG" wait -n "$namespace" --for=condition=Ready "vmi/$vm" --timeout=600s >/dev/null
done
vm_count="$(oc --kubeconfig "$KUBECONFIG" get vm -n "$namespace" -o json | jq '[.items[] | select(.status.printableStatus == "Running")] | length')"
vmi_count="$(oc --kubeconfig "$KUBECONFIG" get vmi -n "$namespace" -o json | jq '[.items[] | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))] | length')"
[[ "$vm_count" -eq "${#vm_names[@]}" && "$vmi_count" -eq "${#vm_names[@]}" ]]

stage=runtime-images
if [[ "$catalog_id" == virtualization-ai-foundations-101 || "$catalog_id" == virtualization-ai-201 ]]; then
  if [[ "$catalog_id" == virtualization-ai-foundations-101 ]]; then
    presentation_deployment=virtualization-ai-presentation
    adapter_deployment=ai-analysis-adapter
  else
    presentation_deployment=virtualization-ai-201-presentation
    adapter_deployment=virtualization-ai-201-adapter
  fi
  presentation_image="$(oc --kubeconfig "$KUBECONFIG" get deployment "$presentation_deployment" -n "$namespace" -o jsonpath='{.spec.template.spec.containers[0].image}')"
  adapter_image="$(oc --kubeconfig "$KUBECONFIG" get deployment "$adapter_deployment" -n "$namespace" -o jsonpath='{.spec.template.spec.containers[0].image}')"
  [[ "$presentation_image" == "$expected_presentation_image" ]]
  [[ "$adapter_image" == "$expected_adapter_image" ]]
fi

stage=presentation
app_host="$(oc --kubeconfig "$KUBECONFIG" get route "$route" -n "$namespace" -o jsonpath='{.spec.host}')"
presentation_status="$(curl -sSL --retry 3 --retry-all-errors --max-time 90 -o /dev/null -w '%{http_code}' "https://${app_host}/")"
[[ "$presentation_status" == 200 ]]

stage=adapter-forward
oc --kubeconfig "$KUBECONFIG" port-forward -n "$namespace" "service/$service" "${forward_port}:8080" >"$work_dir/port-forward.log" 2>&1 &
forward_pid=$!
for _ in {1..30}; do curl -fsS --max-time 2 "http://127.0.0.1:${forward_port}/healthz" >"$work_dir/health.json" && break; sleep 1; done
jq -e . "$work_dir/health.json" >/dev/null

post() { curl -fsS --max-time 30 -H 'Content-Type: application/json' --data-binary "$2" "http://127.0.0.1:${forward_port}$1"; }
normalize_remote_json() {
  # virtctl may emit connection text or terminal control bytes around the
  # remote program's stdout. Decode every possible object boundary and retain
  # only the versioned qualification response, never surrounding transport
  # diagnostics or the VM's stderr receipt.
  python3 -c '
import json
import sys

raw = sys.stdin.read()
decoder = json.JSONDecoder()
for offset, character in enumerate(raw):
    if character != "{":
        continue
    try:
        value, _ = decoder.raw_decode(raw[offset:])
    except json.JSONDecodeError:
        continue
    if isinstance(value, dict) and value.get("schema_version") == "virtualization-ai.redhat-intel.com/qualification-response/v1":
        print(json.dumps(value, separators=(",", ":")))
        raise SystemExit(0)
raise SystemExit("versioned qualification response not found")
'
}
terminal_vm_request() {
  local request_id="$1"
  local condition="$2"
  local response=""
  for _ in {1..40}; do
    if response="$(oc --kubeconfig "$KUBECONFIG" exec -i -n "$namespace" deployment/showroom -c terminal -- \
      bash -s -- "$namespace" "$request_id" "$condition" <<'TERMINAL_VM_REQUEST'
set -euo pipefail
namespace="$1"
request_id="$2"
condition="$3"
key_path=/tmp/launchpad-certification/lab-key
install -d -m 700 "$(dirname "$key_path")"
oc get secret virtualization-ai-model-runtime -n "$namespace" \
  -o jsonpath='{.data.VM_SSH_PRIVATE_KEY}' | base64 -d >"$key_path"
chmod 600 "$key_path"
virtctl ssh --identity-file="$key_path" \
  --local-ssh-opts='-o StrictHostKeyChecking=no' \
  --local-ssh-opts='-o UserKnownHostsFile=/dev/null' \
  -n "$namespace" \
  --command="sudo env LAB_NAMESPACE=$namespace VM_NAME=operations-vm /usr/local/bin/virtualization-ai-client $condition $request_id" \
  lab@vm/operations-vm
TERMINAL_VM_REQUEST
    )"; then
      printf '%s\n' "$response"
      return 0
    fi
    sleep 3
  done
  return 1
}
terminal_contract_author_request() {
  local contract_author_response=""
  for _ in {1..40}; do
    if contract_author_response="$(oc --kubeconfig "$KUBECONFIG" exec -i -n "$namespace" deployment/showroom -c terminal -- \
      bash -s -- "$namespace" 2>&1 <<'TERMINAL_CONTRACT_AUTHOR_REQUEST'
set -euo pipefail
namespace="$1"
key_path=/tmp/launchpad-certification/contract-author-key
install -d -m 700 "$(dirname "$key_path")"
oc get secret virtualization-ai-model-runtime -n "$namespace" \
  -o jsonpath='{.data.VM_SSH_PRIVATE_KEY}' | base64 -d >"$key_path"
chmod 600 "$key_path"
vm_ip="$(oc get vmi contract-author-vm -n "$namespace" -o jsonpath='{.status.interfaces[0].ipAddress}')"
test -n "$vm_ip"
ssh -i "$key_path" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ConnectTimeout=10 \
  learner@"$vm_ip" \
  "sudo env VM_NAMESPACE=$namespace VM_NAME=contract-author-vm /home/learner/vm_client.py 'The application resolves the adapter Service and reaches the governed model boundary.'"
TERMINAL_CONTRACT_AUTHOR_REQUEST
    )"; then
      printf '%s\n' "$contract_author_response"
      return 0
    fi
    sleep 3
  done
  jq -cn --arg phase contract-author-request --arg output "$contract_author_response" \
    '{phase:$phase,output:$output}' | sed 's/^/semantic_response=/' >&2
  return 1
}
stage=adapter-contract
journey_source_state=REHEARSAL
journey_request_origin=certification-client
journey_model_participated=false
journey_model=""
journey_hardware=""
case "$catalog_id" in
  virtualization-ai-foundations-101)
    stage=vm-origin-request
    response="$(terminal_vm_request 11111111-1111-4111-8111-111111111111 healthy)"
    jq -e '.source_state == "LIVE" and .ai_participated == true and .model.hardware == "Intel Xeon CPU" and .validation.schema_valid == true and .validation.category_valid == true and .authority.final_decision_owner == "human operator" and (.authority.actions_permitted | length) == 0' <<<"$response" >/dev/null
    evidence="$(curl -fsS "http://127.0.0.1:18080/api/v1/evidence/11111111-1111-4111-8111-111111111111")"
    jq -e --arg ns "$namespace" '.request_id == "11111111-1111-4111-8111-111111111111" and .origin.kind == "virtual-machine" and .origin.namespace == $ns and .origin.vm_name == "operations-vm"' <<<"$evidence" >/dev/null
    journey_source_state=LIVE
    journey_request_origin=operations-vm
    journey_model_participated=true
    journey_model="$(jq -r '.model.id' <<<"$response")"
    journey_hardware="$(jq -r '.model.hardware' <<<"$response")"
    outcome=live-advisory ;;
  virtualization-ai-201)
    stage=vm-origin-request
    raw_response="$(terminal_contract_author_request)"
    response="$(normalize_remote_json <<<"$raw_response")"
    stage=vm-origin-semantic
    if ! jq -e '.source_state == "LIVE" and .ai_participated == true and .authority == "HUMAN_REVIEW_REQUIRED" and .model.id == "granite-3.2-8b-tools"' <<<"$response" >/dev/null; then
      jq -c '{source_state,ai_participated,outcome,validation,authority,model_id:(.model.id // null),failure_class:(.failure.class // null)}' <<<"$response" \
        | sed 's/^/semantic_response=/' >&2
      false
    fi
    evidence_id="$(jq -r .evidence_id <<<"$response")"
    stage=vm-origin-evidence-fetch
    evidence="$(curl -fsS "http://127.0.0.1:${forward_port}/api/v1/evidence/$evidence_id")"
    stage=vm-origin-evidence-assert
    jq -e --arg ns "$namespace" '.request_sha256 and (.raw_note == null) and .guest == ($ns + "/contract-author-vm") and .service == "virtualization-ai-201-adapter:8080" and .source_state == "LIVE" and .ai_participated == true' <<<"$evidence" >/dev/null
    journey_source_state=LIVE
    journey_request_origin=contract-author-vm
    journey_model_participated=true
    journey_model="$(jq -r '.model.id' <<<"$response")"
    journey_hardware="$(jq -r '.model.hardware' <<<"$response")"
    outcome=qualified ;;
  virtualization-ai-301)
    request="$(jq -cn --arg ns "$namespace" '{schema_version:"virtualization-ai.redhat-intel.com/modernization-request/v1",correlation_id:"30100000-0000-4000-8000-000000000001",task:"review-vm-modernization",note:"Synthetic certification request.",allowed_categories:["identity","connectivity","placement","operations","unknown"],declared:{identity:{namespace:$ns,vm_name:"modernization-client",service_account:"vm-modernization-client"},destination:{service:"virtualization-ai-301-adapter",port:8080},placement:{architecture:"amd64",required_labels:{"feature.node.kubernetes.io/cpu-model.vendor_id":"Intel"}}},observed:{identity:{namespace:$ns,vm_name:"modernization-client",service_account:"vm-modernization-client",vmi_uid:"cert-vmi"},destination:{service:"virtualization-ai-301-adapter",port:8080,network_policy:"ENFORCED",endpoints_ready:true},placement:{node_name:"flightpath-worker",architecture:"amd64",required_labels:{},labels:{"feature.node.kubernetes.io/cpu-model.vendor_id":"Intel"}},observability:{correlation_id:"30100000-0000-4000-8000-000000000001",collected_at:"2026-09-29T12:00:00Z",events_available:true}}}')"
    response="$(post "$endpoint" "$request")"
    jq -e '.outcome == "ALLOW_REVIEW" and .source_state == "REHEARSAL" and .ai_participated == false and .authority == "HUMAN_REVIEW_REQUIRED"' <<<"$response" >/dev/null
    curl -fsS "http://127.0.0.1:${forward_port}/metrics" | grep -q 'virtualization_ai_301_decisions_total'
    outcome=ALLOW_REVIEW ;;
  virtualization-ai-401)
    request='{"schema_version":"demo-story.redhat-intel.com/virtualization-ai-401/operation-request/v1","request_id":"op-401-cert","operation":"LIVE_MIGRATE","target":{"namespace":"cert","virtual_machine":"operations-client"},"requested_by":"certifier","evidence_snapshot":[{"schema_version":"demo-story.redhat-intel.com/virtualization-ai-401/evidence/v1","evidence_id":"ev","request_id":"op-401-cert","state":"OBSERVE","kind":"KUBEVIRT","source":"certification","source_state":"REHEARSAL","observed_at":"2026-09-29T12:00:00Z","freshness":"FRESH","digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","payload":{}}],"preflight":{"identity_match":true,"network_compatible":true,"storage_compatible":true,"evidence_fresh":true,"correlation_complete":true},"approval":null,"observed_result":null}'
    response="$(post "$endpoint" "$request")"
    jq -e '.decision == "ALLOW_REVIEW" and .reason_codes == ["HUMAN_APPROVAL_REQUIRED"] and .authority.automated_action_performed == false' <<<"$response" >/dev/null
    oc --kubeconfig "$KUBECONFIG" rollout restart -n "$namespace" deployment/virtualization-ai-401-operations-adapter >/dev/null
    oc --kubeconfig "$KUBECONFIG" rollout status -n "$namespace" deployment/virtualization-ai-401-operations-adapter --timeout=180s >/dev/null
    [[ "$(oc --kubeconfig "$KUBECONFIG" get pvc virtualization-ai-401-evidence -n "$namespace" -o jsonpath='{.status.phase}')" == Bound ]]
    outcome=ALLOW_REVIEW ;;
  virtualization-ai-501)
    trials='[{"kind":"BASELINE","concurrency":1,"requests":3,"success_rate":1,"p95_ms":100,"cpu_saturation_pct":20,"containment_breaches":0,"correlation_complete":true,"state_continuity":true},{"kind":"MIGRATION","concurrency":1,"requests":3,"success_rate":1,"p95_ms":120,"cpu_saturation_pct":22,"containment_breaches":0,"correlation_complete":true,"state_continuity":true},{"kind":"DISRUPTION","concurrency":1,"requests":3,"success_rate":1,"p95_ms":140,"cpu_saturation_pct":24,"containment_breaches":0,"correlation_complete":true,"state_continuity":true}]'
    request="$(jq -cn --arg ns "$namespace" --argjson trials "$trials" '{schema_version:"demo-story.redhat-intel.com/virtualization-ai-501/qualification-request/v1",request_id:"qualification-cert-001",requested_by:"certifier",fleet:{namespace:$ns,inference_service:"cpu-inference",virtual_machines:[{name:"inference-client-a",node:"worker-a",architecture:"amd64",cpu_vendor:"GenuineIntel"},{name:"inference-client-b",node:"worker-b",architecture:"amd64",cpu_vendor:"GenuineIntel"},{name:"inference-client-c",node:"worker-c",architecture:"amd64",cpu_vendor:"GenuineIntel"}]},envelope:{max_p95_ms:800,min_success_rate:0.98,max_concurrency:12,max_cpu_saturation_pct:90},trials:$trials,evidence_snapshot:[{schema_version:"demo-story.redhat-intel.com/virtualization-ai-501/evidence/v1",evidence_id:"ev",request_id:"qualification-cert-001",state:"DISCOVER",kind:"OPENSHIFT",source:"certification",source_state:"REHEARSAL",observed_at:"2026-09-29T12:00:00Z",freshness:"FRESH",digest:"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",payload:{}}]}')"
    response="$(post "$endpoint" "$request")"
    jq -e '.decision == "ALLOW_REVIEW" and .qualification.status == "PASS" and .qualification.fleet_size == 3 and .authority.promotion_performed == false' <<<"$response" >/dev/null
    [[ "$(oc --kubeconfig "$KUBECONFIG" get pvc virtualization-ai-501-evidence -n "$namespace" -o jsonpath='{.status.phase}')" == Bound ]]
    outcome=ALLOW_REVIEW ;;
esac

stage=terminal-scope
terminal_scope="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom -c terminal -- sh -c '
  printf "project=%s\n" "$(oc project -q)"
  printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")"
  if oc get pods -n launchpad-flightpath-candidate >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
  if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi')"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx own_edit=yes <<<"$terminal_scope"
grep -qx cross_namespace=DENIED <<<"$terminal_scope"
grep -qx node_list=DENIED <<<"$terminal_scope"

stage=console-url
console_url="$(oc --kubeconfig "$KUBECONFIG" whoami --show-console)"
[[ "$console_url" == https://* ]]

jq -cn --arg namespace "$namespace" --arg cluster_ref "$expected_cluster" --arg catalog_id "$catalog_id" \
  --arg outcome "$outcome" --arg source_state "$journey_source_state" --arg request_origin "$journey_request_origin" \
  --arg model "$journey_model" --arg hardware "$journey_hardware" --argjson model_participated "$journey_model_participated" \
  --arg terminal_scope "$terminal_scope" --argjson vm_count "$vm_count" --argjson vmi_count "$vmi_count" \
  --arg source_revision "$source_revision" --arg presentation_image "${presentation_image:-}" --arg adapter_image "${adapter_image:-}" --arg console_url "$console_url" \
  '{result:"GREEN-live-internal-seat",namespace:$namespace,cluster_ref:$cluster_ref,catalog_item_id:$catalog_id,provenance:{source_revision:$source_revision},runtime_images:{presentation:$presentation_image,adapter:$adapter_image},readiness:{vms_running:$vm_count,vmis_ready:$vmi_count,presentation_http_status:200,adapter_health:true},journey:{source_state:$source_state,outcome:$outcome,model_participated:$model_participated,model:$model,hardware:$hardware,intel_placement_verified:(if $catalog_id == "virtualization-ai-301" then false else null end),human_authority_preserved:true,request_origin:$request_origin},operator_journey:{console_url_present:($console_url|startswith("https://")),console_url:$console_url},terminal_scope:($terminal_scope|split("\n")),contains_sensitive_values:false}'
