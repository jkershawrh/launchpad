#!/usr/bin/env bash
set -euo pipefail

namespace="partner-ai-launchpad"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

if [[ $# -ne 2 ]]; then
  echo "usage: $0 /explicit/arena.kubeconfig /explicit/flightpath.kubeconfig" >&2
  exit 2
fi

arena_kubeconfig="$1"
flightpath_kubeconfig="$2"
[[ -f "$arena_kubeconfig" ]] || fail "Arena kubeconfig is not a file"
[[ -f "$flightpath_kubeconfig" ]] || fail "Flightpath kubeconfig is not a file"

arena_server="$(KUBECONFIG="$arena_kubeconfig" oc whoami --show-server)"
flightpath_server="$(KUBECONFIG="$flightpath_kubeconfig" oc whoami --show-server)"
[[ "$arena_server" == *"api.arena.fm2aihpcsed.com"* ]] || fail "Arena kubeconfig points to $arena_server"
[[ "$flightpath_server" == *"api.flightpath.fm2aihpcsed.com"* ]] || fail "Flightpath kubeconfig points to $flightpath_server"
pass "explicit cluster identities verified"

arena_role="$(KUBECONFIG="$arena_kubeconfig" oc -n "$namespace" get configmap launchpad-config -o jsonpath='{.data.LAUNCHPAD_CONTROL_PLANE_ROLE}')"
flightpath_role="$(KUBECONFIG="$flightpath_kubeconfig" oc -n "$namespace" get configmap launchpad-config -o jsonpath='{.data.LAUNCHPAD_CONTROL_PLANE_ROLE}')"
[[ "$arena_role" == "active" ]] || fail "Arena is not the recorded active control plane"
[[ "$flightpath_role" == "standby" ]] || fail "Flightpath is not fail-closed as standby"
pass "active/standby roles verified"

active_flightpath_deployments="$(KUBECONFIG="$flightpath_kubeconfig" oc -n "$namespace" get deployments -o jsonpath='{range .items[?(@.spec.replicas>0)]}{.metadata.name}{"\n"}{end}')"
[[ -z "$active_flightpath_deployments" ]] || fail "Flightpath has active deployments: $active_flightpath_deployments"

unsuspended_cronjobs="$(KUBECONFIG="$flightpath_kubeconfig" oc -n "$namespace" get cronjobs -o jsonpath='{range .items[?(@.spec.suspend!=true)]}{.metadata.name}{"\n"}{end}')"
[[ -z "$unsuspended_cronjobs" ]] || fail "Flightpath has an unsuspended CronJob: $unsuspended_cronjobs"
pass "Flightpath contains no active writer"

for secret_name in \
  launchpad-db-secret \
  launchpad-arena-kubeconfig \
  launchpad-brutus-kubeconfig \
  launchpad-public-access \
  backend-tls \
  backend-oauth-cookie \
  portal-oauth-cookie \
  admin-oauth-cookie \
  launchpad-registry-pull; do
  KUBECONFIG="$flightpath_kubeconfig" oc -n "$namespace" get secret "$secret_name" -o name >/dev/null \
    || fail "required Flightpath Secret $secret_name is missing"
done
pass "restored Secret references are present"

KUBECONFIG="$flightpath_kubeconfig" oc get storageclass ocs-storagecluster-ceph-rbd -o name >/dev/null \
  || fail "Flightpath RBD storage class is unavailable"

pvc_phase="$(KUBECONFIG="$flightpath_kubeconfig" oc -n "$namespace" get pvc postgres-data -o jsonpath='{.status.phase}')"
[[ "$pvc_phase" == "Bound" ]] || fail "Flightpath PostgreSQL PVC is $pvc_phase"
pass "Flightpath storage is ready"

images="$(KUBECONFIG="$flightpath_kubeconfig" oc -n "$namespace" get deployments -o jsonpath='{range .items[*].spec.template.spec.containers[*]}{.image}{"\n"}{end}')"
[[ -n "$images" ]] || fail "no Flightpath workload images were found"
while IFS= read -r image; do
  [[ "$image" == *@sha256:* ]] || fail "image is not digest pinned: $image"
  [[ "$image" != *"image-registry.openshift-image-registry.svc"* ]] \
    || fail "image depends on an execution cluster internal registry: $image"
done <<< "$images"
pass "workload images are immutable and externally reachable"

KUBECONFIG="$flightpath_kubeconfig" oc get crd applications.argoproj.io -o name >/dev/null \
  || fail "Flightpath Argo CD Application CRD is unavailable"

argocd_available_replicas="$(KUBECONFIG="$flightpath_kubeconfig" oc \
  -n openshift-gitops get statefulset \
  openshift-gitops-application-controller \
  -o jsonpath='{.status.availableReplicas}')"
[[ "${argocd_available_replicas:-0}" -ge 1 ]] \
  || fail "Flightpath Argo CD Application controller is unavailable"

KUBECONFIG="$flightpath_kubeconfig" oc -n openshift-gitops \
  get role launchpad-application-manager -o name >/dev/null \
  || fail "Flightpath launchpad-application-manager Role is missing"

backend_identity="system:serviceaccount:${namespace}:launchpad-backend"
can_read_remote_secret="$(KUBECONFIG="$flightpath_kubeconfig" oc auth can-i \
  get secret/launchpad-arena-kubeconfig -n "$namespace" \
  --as="$backend_identity")"
[[ "$can_read_remote_secret" == "yes" ]] \
  || fail "Flightpath backend cannot read the Arena credential Secret"

can_manage_applications="$(KUBECONFIG="$flightpath_kubeconfig" oc auth can-i \
  create applications.argoproj.io -n openshift-gitops \
  --as="$backend_identity")"
[[ "$can_manage_applications" == "yes" ]] \
  || fail "Flightpath backend cannot create Argo CD Applications"

for cluster_spec in \
  "launchpad-arena-argocd-cluster|https://api.arena.fm2aihpcsed.com:6443" \
  "launchpad-brutus-argocd-cluster|https://api.brutus.fm2aihpcsed.com:6443"; do
  IFS='|' read -r argocd_cluster_secret expected_server <<< "$cluster_spec"
  argocd_secret_type="$(KUBECONFIG="$flightpath_kubeconfig" oc \
    -n openshift-gitops get secret "$argocd_cluster_secret" \
    -o jsonpath='{.metadata.labels.argocd\.argoproj\.io/secret-type}')"
  [[ "$argocd_secret_type" == "cluster" ]] \
    || fail "Flightpath Argo CD destination $argocd_cluster_secret is not registered"

  expected_server_b64="$(printf '%s' "$expected_server" | base64 | tr -d '\n')"
  registered_server_b64="$(KUBECONFIG="$flightpath_kubeconfig" oc \
    -n openshift-gitops get secret "$argocd_cluster_secret" \
    -o jsonpath='{.data.server}')"
  [[ "$registered_server_b64" == "$expected_server_b64" ]] \
    || fail "Flightpath Argo CD destination $argocd_cluster_secret points to the wrong API"
done

managed_applications="$(KUBECONFIG="$flightpath_kubeconfig" oc \
  get applications.argoproj.io -A \
  -l app.kubernetes.io/managed-by=launchpad --no-headers 2>/dev/null \
  | wc -l | tr -d ' ')"
[[ "$managed_applications" == "0" ]] \
  || fail "Flightpath passive standby already contains Launchpad Applications"
pass "Flightpath GitOps controller, backend RBAC, and execution destinations are ready and passive"

public_enabled="$(KUBECONFIG="$flightpath_kubeconfig" oc -n "$namespace" get configmap launchpad-config -o jsonpath='{.data.PUBLIC_ACCESS_ENABLED}')"
[[ "$public_enabled" == "false" ]] || fail "public access must remain disabled for the first promotion drill"
pass "public access remains gated"

echo "Flightpath promotion preflight: GREEN (read-only checks only)"
