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

`OpenShiftProvisioningAdapter._grant_image_pull` currently creates an
`image-puller` RoleBinding in `partner-ai-launchpad`. Flightpath's admission
policy denies that write for its provisioner, and this adapter currently
swallows non-409 errors from the attempt. A green static RBAC test therefore
does **not** prove the image-pull path. Resolve the need for cross-namespace
pulls, choose a narrowly scoped identity/exception or an external registry,
and make the grant failure observable before using the reference as a live
replacement. Do not broadly allow writes in `partner-ai-launchpad` merely to
make the test pass.

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
