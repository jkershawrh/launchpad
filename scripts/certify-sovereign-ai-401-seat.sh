#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-sovereign-ai-401-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-sovereign-ai-401-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"

stage="setup"; work_dir="$(mktemp -d)"; pf_pid=""
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
cleanup() { [[ -z "$pf_pid" ]] || kill "$pf_pid" >/dev/null 2>&1 || true; rm -rf "$work_dir"; }
trap cleanup EXIT

stage="route-discovery"
app_host="$(oc --kubeconfig "$KUBECONFIG" get route story -n "$namespace" -o jsonpath='{.spec.host}')"
[[ -n "$app_host" ]]
presentation_status="$(curl -fsSL --max-time 30 -o /dev/null -w '%{http_code}' "https://${app_host}/")"; [[ "$presentation_status" == "200" ]]

stage="qualifier-forward"
oc --kubeconfig "$KUBECONFIG" port-forward -n "$namespace" service/sovereign-ai-401-qualifier 18401:8080 >"$work_dir/port-forward.log" 2>&1 & pf_pid=$!
for _ in {1..30}; do curl -fsS --max-time 2 http://127.0.0.1:18401/healthz >"$work_dir/health" && break; sleep 1; done
jq -e '.status == "ok" and .sourceState == "REHEARSAL"' "$work_dir/health" >/dev/null

stage="qualification"
scenarios="$(curl -fsS --max-time 15 http://127.0.0.1:18401/api/v1/scenarios)"
jq -e '.liveTdxObserved == false and (.scenarios|index("authorized")) and (.scenarios|index("simulated_live_claim"))' <<<"$scenarios" >/dev/null
curl -fsS --max-time 15 -X POST http://127.0.0.1:18401/api/v1/reset >/dev/null
allowed="$(curl -fsS --max-time 15 -H 'Content-Type: application/json' -d '{"scenario":"authorized"}' http://127.0.0.1:18401/api/v1/operate)"
jq -e '.decision == "ALLOW_REVIEW" and .sourceState == "REHEARSAL" and .observation.confidentialGuestRunning == false and .observation.liveTdxQuoteVerified == false and .protectedResource.mode == "SYNTHETIC_RECEIPT_ONLY" and .protectedResource.keyMaterialReleased == false and .inference.modelInvoked == false and .evidenceChain.verified == true and .authority.certified == false and .authority.llmAuthority == "NONE"' <<<"$allowed" >/dev/null
false_live="$(curl -fsS --max-time 15 -H 'Content-Type: application/json' -d '{"scenario":"simulated_live_claim"}' http://127.0.0.1:18401/api/v1/operate)"
jq -e '.decision == "REFUSE" and .sourceState == "REHEARSAL" and (.reasonCodes|index("FALSE_LIVE_CLAIM")) and .protectedResource.keyMaterialReleased == false and .inference.modelInvoked == false' <<<"$false_live" >/dev/null

stage="terminal-scope"
terminal_scope="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom -c terminal -- sh -c '
  printf "project=%s\n" "$(oc project -q)"; printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")";
  if oc get pods -n launchpad-flightpath-candidate >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
  if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
')"
grep -qx "project=${namespace}" <<<"$terminal_scope"; grep -qx 'own_edit=yes' <<<"$terminal_scope"; grep -qx 'cross_namespace=DENIED' <<<"$terminal_scope"; grep -qx 'node_list=DENIED' <<<"$terminal_scope"

stage="console-surface"
console_url="$(oc --kubeconfig "$KUBECONFIG" whoami --show-console)"
[[ "$console_url" == https://* ]]

stage="runtime-stability"
presentation_restarts="$(oc --kubeconfig "$KUBECONFIG" get pods -n "$namespace" -l app.kubernetes.io/name=sovereign-ai-401-presentation -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')"
[[ "$presentation_restarts" == "0" ]]

jq -cn --arg namespace "$namespace" --arg cluster_ref "$expected_cluster" --arg terminal_scope "$terminal_scope" --arg console_url "$console_url" --argjson presentation_restarts "$presentation_restarts" '{result:"GREEN-live-internal-seat",namespace:$namespace,cluster_ref:$cluster_ref,readiness:{qualifier_health:true,presentation_http_status:200,presentation_restarts:$presentation_restarts},journey:{mode:"REHEARSAL",live_tdx_observed:false,allow_path:"ALLOW_REVIEW",false_live_path:"REFUSE",synthetic_receipt_only:true,key_material_released:false,model_invoked:false,evidence_chain_valid:true,human_authority_retained:true},operator_journey:{terminal_scope_verified:true,console_url_present:($console_url|startswith("https://")),qualification_service_verified:true},terminal_scope:($terminal_scope|split("\n")),contains_sensitive_values:false}'
