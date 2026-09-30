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

cleanup() {
  [[ -z "$forward_pid" ]] || kill "$forward_pid" >/dev/null 2>&1 || true
  oc --kubeconfig "$KUBECONFIG" delete rolebinding "$probe_binding" -n "$namespace" --ignore-not-found >/dev/null 2>&1 || true
  rm -rf "$work_dir"
}
trap cleanup EXIT

oc --kubeconfig "$KUBECONFIG" create rolebinding "$probe_binding" --clusterrole=edit \
  --serviceaccount="$probe_serviceaccount" -n "$namespace" --dry-run=client -o yaml \
  | oc --kubeconfig "$KUBECONFIG" apply -f - >/dev/null

case "$catalog_id" in
  virtualization-ai-foundations-101)
    vm_names=(operations-vm); service=ai-analysis; route=lab; endpoint=/api/v1/analyze ;;
  virtualization-ai-201)
    vm_names=(contract-author-vm); service=virtualization-ai-201-adapter; route=lab; endpoint=/api/v1/qualify ;;
  virtualization-ai-301)
    vm_names=(modernization-client); service=virtualization-ai-301-adapter; route=virtualization-ai-301; endpoint=/api/v1/modernize ;;
  virtualization-ai-401)
    vm_names=(operations-client); service=virtualization-ai-401-operations-adapter; route=virtualization-ai-401; endpoint=/api/v1/operations ;;
  virtualization-ai-501)
    vm_names=(inference-client-a inference-client-b inference-client-c); service=virtualization-ai-501-qualification-adapter; route=virtualization-ai-501; endpoint=/api/v1/qualifications ;;
  *) printf 'unsupported catalog: %s\n' "$catalog_id" >&2; exit 2 ;;
esac

stage=vm-ready
for vm in "${vm_names[@]}"; do
  oc --kubeconfig "$KUBECONFIG" wait -n "$namespace" --for=jsonpath='{.status.printableStatus}'=Running "vm/$vm" --timeout=600s >/dev/null
  oc --kubeconfig "$KUBECONFIG" wait -n "$namespace" --for=condition=Ready "vmi/$vm" --timeout=600s >/dev/null
done
vm_count="$(oc --kubeconfig "$KUBECONFIG" get vm -n "$namespace" -o json | jq '[.items[] | select(.status.printableStatus == "Running")] | length')"
vmi_count="$(oc --kubeconfig "$KUBECONFIG" get vmi -n "$namespace" -o json | jq '[.items[] | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))] | length')"
[[ "$vm_count" -eq "${#vm_names[@]}" && "$vmi_count" -eq "${#vm_names[@]}" ]]

stage=presentation
app_host="$(oc --kubeconfig "$KUBECONFIG" get route "$route" -n "$namespace" -o jsonpath='{.spec.host}')"
presentation_status="$(curl -sSkL --retry 3 --retry-all-errors --max-time 90 -o /dev/null -w '%{http_code}' "https://${app_host}/")"
[[ "$presentation_status" == 200 ]]

stage=adapter-forward
oc --kubeconfig "$KUBECONFIG" port-forward -n "$namespace" "service/$service" 18080:8080 >"$work_dir/port-forward.log" 2>&1 &
forward_pid=$!
for _ in {1..30}; do curl -fsS --max-time 2 http://127.0.0.1:18080/healthz >"$work_dir/health.json" && break; sleep 1; done
jq -e . "$work_dir/health.json" >/dev/null

post() { curl -fsS --max-time 30 -H 'Content-Type: application/json' --data-binary "$2" "http://127.0.0.1:18080$1"; }
stage=adapter-contract
case "$catalog_id" in
  virtualization-ai-foundations-101)
    request="$(jq -cn --arg ns "$namespace" '{schema_version:"analysis-request/v1",request_id:"11111111-1111-4111-8111-111111111111",origin:{kind:"virtual-machine",namespace:$ns,vm_name:"operations-vm",guest_hostname:"operations-vm"},note:"Synthetic operations note for certification.",allowed_categories:["inspect","schedule-maintenance","escalate"],condition:"healthy"}')"
    response="$(post "$endpoint" "$request")"
    jq -e '.source_state == "LIVE" and .ai_participated == true and .model.hardware == "Intel Xeon CPU" and .validation.schema_valid == true and .validation.category_valid == true and .authority.final_decision_owner == "human operator" and (.authority.actions_permitted | length) == 0' <<<"$response" >/dev/null
    evidence="$(curl -fsS "http://127.0.0.1:18080/api/v1/evidence/11111111-1111-4111-8111-111111111111")"
    jq -e '.request_id == "11111111-1111-4111-8111-111111111111"' <<<"$evidence" >/dev/null
    outcome=live-advisory ;;
  virtualization-ai-201)
    request="$(jq -cn --arg ns "$namespace" '{schema_version:"virtualization-ai.redhat-intel.com/qualification-request/v1",correlation_id:"11111111-1111-4111-8111-111111111111",guest:{name:"contract-author-vm",namespace:$ns},task:"classify-operations-note",note:"The Service resolves but the downstream model boundary is unavailable.",allowed_categories:["application","capacity","connectivity","unknown"]}')"
    response="$(post "$endpoint" "$request")"
    jq -e '.source_state == "REHEARSAL" and .authority == "HUMAN_REVIEW_REQUIRED" and .advisory.category == "connectivity"' <<<"$response" >/dev/null
    evidence_id="$(jq -r .evidence_id <<<"$response")"
    curl -fsS "http://127.0.0.1:18080/api/v1/evidence/$evidence_id" | jq -e '.request_sha256 and (.raw_note == null)' >/dev/null
    outcome=qualified ;;
  virtualization-ai-301)
    request="$(jq -cn --arg ns "$namespace" '{schema_version:"virtualization-ai.redhat-intel.com/modernization-request/v1",correlation_id:"30100000-0000-4000-8000-000000000001",task:"review-vm-modernization",note:"Synthetic certification request.",allowed_categories:["identity","connectivity","placement","operations","unknown"],declared:{identity:{namespace:$ns,vm_name:"modernization-client",service_account:"vm-modernization-client"},destination:{service:"virtualization-ai-301-adapter",port:8080},placement:{architecture:"amd64",required_labels:{"feature.node.kubernetes.io/cpu-model.vendor_id":"Intel"}}},observed:{identity:{namespace:$ns,vm_name:"modernization-client",service_account:"vm-modernization-client",vmi_uid:"cert-vmi"},destination:{service:"virtualization-ai-301-adapter",port:8080,network_policy:"ENFORCED",endpoints_ready:true},placement:{node_name:"flightpath-worker",architecture:"amd64",required_labels:{},labels:{"feature.node.kubernetes.io/cpu-model.vendor_id":"Intel"}},observability:{correlation_id:"30100000-0000-4000-8000-000000000001",collected_at:"2026-09-29T12:00:00Z",events_available:true}}}')"
    response="$(post "$endpoint" "$request")"
    jq -e '.outcome == "ALLOW_REVIEW" and .source_state == "REHEARSAL" and .ai_participated == false and .authority == "HUMAN_REVIEW_REQUIRED"' <<<"$response" >/dev/null
    curl -fsS http://127.0.0.1:18080/metrics | grep -q 'virtualization_ai_301_decisions_total'
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

jq -cn --arg namespace "$namespace" --arg cluster_ref "$expected_cluster" --arg catalog_id "$catalog_id" \
  --arg outcome "$outcome" --arg terminal_scope "$terminal_scope" --argjson vm_count "$vm_count" --argjson vmi_count "$vmi_count" \
  '{result:"GREEN-live-internal-seat",namespace:$namespace,cluster_ref:$cluster_ref,catalog_item_id:$catalog_id,readiness:{vms_running:$vm_count,vmis_ready:$vmi_count,presentation_http_status:200,adapter_health:true},journey:{source_state:(if $catalog_id == "virtualization-ai-foundations-101" then "LIVE" else "REHEARSAL" end),outcome:$outcome,human_authority_preserved:true},terminal_scope:($terminal_scope|split("\n")),contains_sensitive_values:false}'
