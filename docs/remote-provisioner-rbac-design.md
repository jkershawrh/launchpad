# Remote provisioner RBAC: disposable-cluster design contract

Status: **design only**. Do not apply this document or narrow the active
Arena, Brutus, or Flightpath bindings while retained labs are running.
Flightpath's `deploy/multicluster/flightpath-remote-rbac.yaml` is the reference,
not a production certification of this replacement.

## Boundary

- Keep a distinct service account per control plane and execution cluster.
  The cluster-bound bootstrap role may discover capacity, create/delete owned
  namespaces, and create namespaced RoleBindings. It must not gain global
  Secret, workload, or Route writes.
- Bind the provisioner and Argo CD seat-manager ClusterRoles through
  RoleBindings **inside each Launchpad-owned namespace only**. Never bind
  those roles with ClusterRoleBindings. Reconcile the bindings after namespace
  creation and before any seat resource or Argo CD application is submitted.
- A fail-closed admission policy must restrict bootstrap mutations to
  `launchpad-*` namespaces. `bind` permission is limited to the exact
  seat-manager and participant ClusterRoles required by provisioning.
- Cleanup must use the persisted target cluster and delete the same seat
  namespace. Missing, stale, or unavailable credentials fail closed; they do
  not trigger fallback to another cluster or a broader identity.

## Known gap before a disposable proof

`OpenShiftProvisioningAdapter._grant_image_pull` creates an `image-puller`
RoleBinding in `partner-ai-launchpad`; Flightpath's admission policy denies
that write for its provisioner. The adapter now skips the grant only for
operator-style labs whose Showroom images are explicitly Quay digest refs and
whose optional workload is the known single-image multi-agent chart with a
Quay digest ref. Missing image refs, unknown charts, internal-registry images,
and gateway-backed labs still require the grant. Non-409 API errors now fail
provisioning instead of being swallowed. This is a **local code contract**, not
live Flightpath certification: the external images must be pull-tested there,
and gateway-backed Flightpath labs remain blocked until their image source or
narrowly scoped grant path is resolved. Do not broadly allow writes in
`partner-ai-launchpad` merely to make a test pass.

## Evidence required to promote

1. In a disposable target, start from no seat namespace and use only the
   proposed provisioner and Argo CD identities. Prove the namespace and its
   scoped RoleBindings appear in order; missing bindings must stop work.
2. Prove a one-seat lab's images, secrets, routes, Showroom, workspace, and
   Console access, then validate, expire, manually reclaim, and reconcile an
   interrupted cleanup. Repeat for gateway-backed and operator-style labs.
3. Negative checks: both identities cannot read another tenant's Secrets,
   write outside a `launchpad-*` namespace, bind `cluster-admin`, or create a
   ClusterRoleBinding. Record `SelfSubjectAccessReview` and server-side denied
   writes rather than inferring isolation from YAML alone.
4. Prove zero residue (namespace, RoleBinding, Route, Application, and Secret)
   and successful credential rotation/restart. Then do a rendered-manifest
   diff and a controlled one-seat live canary with a rollback identity before
   considering any change to active roles.

Local guardrails: `backend/tests/test_remote_scoped_rbac_contract.py` checks
the reference manifest's global binding and admission invariants. These are
source contracts, not live authorization evidence.
`backend/tests/test_openshift_image_pull_grant.py` also reads the deployed Arena
cluster-target overlay and all three pilot catalog items, builds their plans,
and verifies that only Flightpath's pinned external-image paths skip the
cross-namespace grant. It checks the known multi-agent chart's image fields;
it does not prove registry reachability, pull permissions, or runtime behavior.

Run `.venv/bin/python scripts/flightpath_execution_preflight.py` for a
read-only JSON summary of this source gate. A `static_contract_passed` result
does not certify an execution seat: the report leaves image pulls, model calls,
Showroom/workspace access, and zero-residue reclaim as `not_run`. The separate
DR standby preflight likewise checks image references, not actual pullability.
Add `--probe-registry` to make anonymous HTTPS HEAD requests for each configured
Quay manifest and verify the response digest. This proves manifest availability
from the machine running the check, not layer pullability from Flightpath.
