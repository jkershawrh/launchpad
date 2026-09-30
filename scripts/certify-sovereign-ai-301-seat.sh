#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-sovereign-ai-301-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-sovereign-ai-301-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

stage="setup"; work_dir="$(mktemp -d)"; pf_pid=""
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
cleanup() { [[ -z "$pf_pid" ]] || kill "$pf_pid" >/dev/null 2>&1 || true; rm -rf "$work_dir"; }
trap cleanup EXIT

stage="route-discovery"
app_host="$(oc --kubeconfig "$KUBECONFIG" get route story -n "$namespace" -o jsonpath='{.spec.host}')"
[[ -n "$app_host" ]]
presentation_status="$(curl -fsSL --max-time 30 -o /dev/null -w '%{http_code}' "https://${app_host}/")"
[[ "$presentation_status" == "200" ]]

stage="qualifier-forward"
oc --kubeconfig "$KUBECONFIG" port-forward -n "$namespace" service/sovereign-ai-301 18301:8080 >"$work_dir/port-forward.log" 2>&1 & pf_pid=$!
for _ in {1..30}; do curl -fsS --max-time 2 http://127.0.0.1:18301/healthz >"$work_dir/health" && break; sleep 1; done
jq -e '.status == "ok" and .sourceState == "REHEARSAL"' "$work_dir/health" >/dev/null

stage="qualification"
scenarios="$(curl -fsS --max-time 15 http://127.0.0.1:18301/api/v1/scenarios)"
jq -e '.liveTdxObserved == false and (.scenarios|index("allowed")) and (.scenarios|index("invalid_measurement"))' <<<"$scenarios" >/dev/null
curl -fsS --max-time 15 -X POST http://127.0.0.1:18301/api/v1/reset >/dev/null
allowed="$(curl -fsS --max-time 15 -H 'Content-Type: application/json' -d '{"scenario":"allowed"}' http://127.0.0.1:18301/api/v1/qualify)"
jq -e '.decision == "ALLOW_SYNTHETIC_RELEASE" and .sourceState == "REHEARSAL" and .liveTdxObserved == false and .keyRelease.mode == "SYNTHETIC_RECEIPT_ONLY" and .keyMaterialReleased == false and .modelInvoked == false and .humanAuthority.certified == false and .humanAuthority.promotionEligible == false' <<<"$allowed" >/dev/null
denied="$(curl -fsS --max-time 15 -H 'Content-Type: application/json' -d '{"scenario":"invalid_measurement"}' http://127.0.0.1:18301/api/v1/qualify)"
jq -e '.decision == "DENY_MEASUREMENT" and .sourceState == "REHEARSAL" and .resourcePolicy.allowed == false and .keyMaterialReleased == false and .modelInvoked == false' <<<"$denied" >/dev/null

stage="terminal-scope"
terminal_scope="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom -c terminal -- sh -c '
  printf "project=%s\n" "$(oc project -q)"; printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")";
  if oc get pods -n launchpad-flightpath-candidate >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
  if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
')"
grep -qx "project=${namespace}" <<<"$terminal_scope"; grep -qx 'own_edit=yes' <<<"$terminal_scope"; grep -qx 'cross_namespace=DENIED' <<<"$terminal_scope"; grep -qx 'node_list=DENIED' <<<"$terminal_scope"

jq -cn --arg namespace "$namespace" --arg cluster_ref "$expected_cluster" --arg terminal_scope "$terminal_scope" '{result:"GREEN-live-internal-seat",namespace:$namespace,cluster_ref:$cluster_ref,readiness:{qualifier_health:true,presentation_http_status:200},journey:{mode:"REHEARSAL",live_tdx_observed:false,confidential_runtime_enabled:false,hardware_quote_verified:false,trustee_verified:false,allow_path:"ALLOW_SYNTHETIC_RELEASE",deny_path:"DENY_MEASUREMENT",synthetic_receipt_only:true,key_material_released:false,inference_authorized:false,model_invoked:false,human_authority_retained:true},terminal_scope:($terminal_scope|split("\n")),contains_sensitive_values:false}'
