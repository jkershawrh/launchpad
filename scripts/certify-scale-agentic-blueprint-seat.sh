#!/usr/bin/env bash
set -euo pipefail

namespace="${1:?usage: certify-scale-agentic-blueprint-seat.sh <namespace> <cluster-id>}"
expected_cluster="${2:?usage: certify-scale-agentic-blueprint-seat.sh <namespace> <cluster-id>}"
: "${KUBECONFIG:?KUBECONFIG must point to the expected execution cluster credential}"
source_revision="960d295025faf3d8f45bb916163a90ec4e43770a"
expected_presentation_image="ghcr.io/jkershawrh/agentic-scale-501-presentation@sha256:cfbb376c62903a96e4c85a5e2bcceaa663d915a109b69df4c20a21f4e3bf882b"
expected_qualifier_image="ghcr.io/jkershawrh/agentic-scale-501-qualifier@sha256:160c9cf301dd0699e5eaf130c7eb9632051fd959a1e28001ec460d85488ef0a3"

stage="setup"
trap 'rc=$?; printf "seat_probe_failure stage=%s exit_code=%s\n" "$stage" "$rc" >&2' ERR
probe_binding="launchpad-certification-probe"
probe_serviceaccount="${LAUNCHPAD_CERTIFICATION_SERVICEACCOUNT:-partner-ai-launchpad:launchpad-provisioner}"
cleanup_probe_access() {
  oc --kubeconfig "$KUBECONFIG" delete rolebinding "$probe_binding" \
    --namespace "$namespace" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup_probe_access EXIT
oc --kubeconfig "$KUBECONFIG" create rolebinding "$probe_binding" \
  --clusterrole=edit \
  --serviceaccount="$probe_serviceaccount" \
  --namespace "$namespace" --dry-run=client -o yaml \
  | oc --kubeconfig "$KUBECONFIG" apply -f - >/dev/null

stage="workload-readiness"
oc --kubeconfig "$KUBECONFIG" rollout status deployment/agentic-scale-501-presentation \
  -n "$namespace" --timeout=300s >/dev/null
oc --kubeconfig "$KUBECONFIG" rollout status deployment/agentic-scale-501-qualifier \
  -n "$namespace" --timeout=300s >/dev/null

stage="runtime-images"
presentation_image="$(oc --kubeconfig "$KUBECONFIG" get deployment agentic-scale-501-presentation -n "$namespace" -o jsonpath='{.spec.template.spec.containers[0].image}')"
qualifier_image="$(oc --kubeconfig "$KUBECONFIG" get deployment agentic-scale-501-qualifier -n "$namespace" -o jsonpath='{.spec.template.spec.containers[0].image}')"
[[ "$presentation_image" == "$expected_presentation_image" ]]
[[ "$qualifier_image" == "$expected_qualifier_image" ]]
presentation_image_id="$(oc --kubeconfig "$KUBECONFIG" get pod -n "$namespace" -l app.kubernetes.io/name=agentic-scale-501-presentation -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')"
qualifier_image_id="$(oc --kubeconfig "$KUBECONFIG" get pod -n "$namespace" -l app.kubernetes.io/name=agentic-scale-501-qualifier -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')"
[[ "$presentation_image_id" == *"${expected_presentation_image#*@}" ]]
[[ "$qualifier_image_id" == *"${expected_qualifier_image#*@}" ]]
presentation_restarts="$(oc --kubeconfig "$KUBECONFIG" get pod -n "$namespace" -l app.kubernetes.io/name=agentic-scale-501-presentation -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')"
[[ "$presentation_restarts" == "0" ]]

stage="route-discovery"
presentation_host="$(oc --kubeconfig "$KUBECONFIG" get route agentic-scale-501-presentation \
  -n "$namespace" -o jsonpath='{.spec.host}')"
qualifier_host="$(oc --kubeconfig "$KUBECONFIG" get route agentic-scale-501-qualifier \
  -n "$namespace" -o jsonpath='{.spec.host}')"
curl_options=(-fsS --retry 4 --retry-all-errors --retry-delay 2 --max-time 180)

stage="presentation"
presentation="$(curl "${curl_options[@]}" "https://${presentation_host}/")"
grep -q 'Production Multi-Agent Blueprint' <<<"$presentation"
presentation_asset_path="$(sed -n 's/.*<script[^>]*src="\([^"]*\.js\)".*/\1/p' <<<"$presentation" | head -1)"
[[ "$presentation_asset_path" == /* ]]
presentation_bundle="$(curl "${curl_options[@]}" "https://${presentation_host}${presentation_asset_path}")"
grep -q 'SCALE PROOF' <<<"$presentation_bundle"
! grep -q 'LIVE WORKLOAD' <<<"$presentation_bundle"

stage="qualifier-health"
jq -e '.status == "ok"' <<<"$(curl "${curl_options[@]}" "https://${qualifier_host}/healthz")" >/dev/null
jq -e '.status == "ready"' <<<"$(curl "${curl_options[@]}" "https://${qualifier_host}/readyz")" >/dev/null

stage="qualification-operator"
qualification_status="$(curl "${curl_options[@]}" "https://${qualifier_host}/api/v1/status")"
grep -q 'Qualification Evidence' <<<"$qualification_status"
grep -q 'REHEARSAL' <<<"$qualification_status"
grep -q 'Human review required' <<<"$qualification_status"
grep -q 'No model participated' <<<"$qualification_status"

stage="rehearsal-qualification"
profile="$(jq -cn '{profile:{
  id:"flightpath-destination-qualification",
  version:"policy-v1",
  phase:"baseline",
  workloadImageDigest:"sha256:160c9cf301dd0699e5eaf130c7eb9632051fd959a1e28001ec460d85488ef0a3",
  evaluationSetVersion:"agentic-scale-501-v1",
  target:"flightpath/agentic-scale-501",
  concurrency:1,
  journeys:3
}}')"
proof="$(curl "${curl_options[@]}" -X POST "https://${qualifier_host}/api/scale/run" \
  -H 'Content-Type: application/json' --data-binary "$profile")"
jq -e '
  .schemaVersion == "agentic-scale-proof/v1"
  and .source == "rehearsal"
  and .inference.model == "deterministic-rehearsal-model"
  and .inference.endpoint == "local://agentic-scale-501/rehearsal"
  and .workload.attemptedJourneys == 3
  and .workload.completedJourneys == 3
  and .workload.errorCount == 0
  and .correlation.completeJourneys == 3
  and .policy.unauthorizedActions == 0
  and .authority.automatedPromotion == false
  and .authority.humanReviewRequired == true
  and .authority.reviewerDisposition == "pending"
' <<<"$proof" >/dev/null

stage="terminal-scope"
terminal_scope="$(oc --kubeconfig "$KUBECONFIG" exec -n "$namespace" deployment/showroom \
  -c terminal -- sh -c '
    printf "project=%s\n" "$(oc project -q)"
    printf "own_edit=%s\n" "$(oc auth can-i create deployments.apps -n "$PROJECT_NAME")"
    if oc get pods -n launchpad-flightpath-candidate >/dev/null 2>&1; then echo cross_namespace=ALLOWED; else echo cross_namespace=DENIED; fi
    if oc get nodes >/dev/null 2>&1; then echo node_list=ALLOWED; else echo node_list=DENIED; fi
  ')"
grep -qx "project=${namespace}" <<<"$terminal_scope"
grep -qx 'own_edit=yes' <<<"$terminal_scope"
grep -qx 'cross_namespace=DENIED' <<<"$terminal_scope"
grep -qx 'node_list=DENIED' <<<"$terminal_scope"

stage="console-url"
console_url="$(oc --kubeconfig "$KUBECONFIG" whoami --show-console)"
[[ "$console_url" == https://* ]]

stage="evidence"
jq -cn \
  --arg namespace "$namespace" \
  --arg cluster_ref "$expected_cluster" \
  --arg presentation_host "$presentation_host" \
  --arg qualifier_host "$qualifier_host" \
  --arg terminal_scope "$terminal_scope" \
  --arg source_revision "$source_revision" \
  --arg presentation_image "$presentation_image" \
  --arg qualifier_image "$qualifier_image" \
  --arg console_url "$console_url" \
  --argjson presentation_restarts "$presentation_restarts" \
  --argjson proof "$proof" \
  '{
    result: "GREEN-destination-rehearsal-seat",
    namespace: $namespace,
    cluster_ref: $cluster_ref,
    readiness: {presentation: true, qualifier: true, routes: true},
    evidence_source: $proof.source,
    live_claim: false,
    provenance: {source_revision: $source_revision},
    runtime_images: {
      presentation: $presentation_image,
      qualifier: $qualifier_image
    },
    inference: {
      synthetic: true,
      fixture_model: $proof.inference.model,
      fixture_endpoint: $proof.inference.endpoint,
      model_participated: false
    },
    presentation_host: $presentation_host,
    qualifier_host: $qualifier_host,
    presentation_restarts: $presentation_restarts,
    operator_journey: {
      terminal_scope_verified: true,
      console_url_present: ($console_url | startswith("https://")),
      qualification_service_verified: true,
      qualification_status_page_verified: true,
      console_url: $console_url
    },
    qualification: {
      schema: $proof.schemaVersion,
      attempted_journeys: $proof.workload.attemptedJourneys,
      completed_journeys: $proof.workload.completedJourneys,
      correlation_complete: $proof.correlation.completeJourneys,
      automated_promotion: $proof.authority.automatedPromotion,
      human_review_required: $proof.authority.humanReviewRequired
    },
    terminal_scope: ($terminal_scope | split("\n")),
    contains_sensitive_values: false
  }'
