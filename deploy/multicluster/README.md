# Remote execution-cluster registration

Arena is the current local control and execution cluster. Oberon and Brutus are
registered in the Arena cluster-target ConfigMap as disabled remote targets.
They must remain disabled until the complete procedure below and the catalog's
1 -> 5 -> 25 live certification are green.

As of 2026-09-05, Brutus has passed the one-seat gate and a warm five-seat
functional run covering Showroom, terminals, simultaneous Build-an-Agent tool
calling, namespace isolation, and zero-residue bulk reclaim. It remains
disabled for normal placement because the CA-verification regression still
needs a deployed live rerun and the twenty-five-seat gate has not passed. Its
integrated registry now uses a retained 100Gi NFS claim and all three pinned
images passed post-restart `Always` pull probes. Oberon remains at the
infrastructure probe gate.

Apply `arena-rbac.yaml` only to a remote execution cluster, create a bound
service-account token, and build a kubeconfig for that identity. Despite the
historical filename, this is the shared Launchpad provisioner RBAC contract.
Never apply it to Arena while Arena hosts the control plane. Use one credential
per remote cluster; do not reuse a token between Brutus and Oberon. Store each
kubeconfig on Arena without committing it:

```sh
KUBECONFIG=/explicit/arena-admin.kubeconfig oc \
  -n partner-ai-launchpad create secret generic launchpad-brutus-kubeconfig \
  --from-file=kubeconfig=/secure/path/brutus-launchpad.kubeconfig
```

Use `launchpad-oberon-kubeconfig` for Oberon. The Secret names and namespaces
must exactly match `credential_secret` in `config/clusters.yaml`.

Apply `arena-argocd-rbac.yaml` to the remote cluster with an explicit
kubeconfig, then register that separate Argo identity in Arena's existing Argo
CD using its supported cluster-secret workflow. The Argo destination servers
must exactly match the registry:

- Brutus: `https://api.brutus.fm2aihpcsed.com:6443`
- Oberon: `https://api.oberon.fm2aihpcsed.com:6443`

Never copy kubeadmin credentials into Launchpad or Git.

## Control-plane ownership and cutover safety

Every control plane must set a unique `LAUNCHPAD_CONTROL_PLANE_ID`. The Arena
overlay uses `arena-primary`; the Oberon overlay uses `oberon-primary`.
Launchpad stamps that identity on every managed namespace, and orphan
reconciliation selects only namespaces carrying its own identity. Orphan
deletion also fails closed when either the control-plane identity or database
connection is unavailable.

Before moving the control plane, revoke the old control plane's remote
credential on every execution cluster. A stale reconciler with a different
session database must never retain namespace-delete permission after cutover.
On the new local control-plane cluster, verify that no workload uses the remote
provisioner identity, then remove its binding and service account:

```sh
KUBECONFIG=/explicit/arena-admin.kubeconfig oc get pods -A \
  -o jsonpath='{range .items[?(@.spec.serviceAccountName=="launchpad-provisioner")]}{.metadata.namespace}/{.metadata.name}{"\\n"}{end}'
KUBECONFIG=/explicit/arena-admin.kubeconfig oc delete \
  clusterrolebinding launchpad-remote-provisioner
KUBECONFIG=/explicit/arena-admin.kubeconfig oc -n partner-ai-launchpad delete \
  serviceaccount launchpad-provisioner
```

These removals are intentional and recoverable by applying the remote RBAC
manifest during a future, deliberate topology change. Recreating the service
account produces a new identity and does not revive an old credential.

Build the control-plane trust bundle from explicit, authenticated kubeconfigs
before enabling an HTTPS model endpoint on a remote target:

```sh
scripts/install-cluster-ca-bundle.sh \
  /secure/arena-admin.kubeconfig \
  partner-ai-launchpad \
  backend \
  /secure/arena-admin.kubeconfig \
  /secure/brutus-admin.kubeconfig \
  /secure/oberon-admin.kubeconfig
```

The script combines the backend image's system roots with every execution
cluster ingress chain, mounts the result, and enables verification for both
`httpx` and `requests`. Launchpad copies that bundle into model-consuming seat
namespaces. Re-run it whenever an ingress certificate rotates; never disable
TLS verification to make a remote model probe pass.

The Argo identity has cluster-wide read access because its cache discovers
cluster resource kinds, while mutation remains limited to the resources used
by Showroom. Do not reuse the Argo credential for Launchpad provisioning.

Before enabling a remote target, prove all of the following from the Arena
control plane:

1. Launchpad and Argo credentials resolve and have only the documented access.
2. Namespace, Route, PVC, workload, Showroom, validation, and reclaim target
   only the persisted remote `cluster_ref`.
3. Durable images pull without relying on another execution cluster's internal
   registry. Pre-seed and verify every immutable digest before opening an
   order; the Brutus one-seat run measured a 10m42s cold terminal-image mirror
   and one resumable HTTP 408 while moving the agent image. Brutus now stores
   its mirror on a retained NFS claim and has passed exact-digest pulls after a
   registry restart; repeat that proof whenever the pinned image set changes.
4. Every required model endpoint is reachable from the remote workload network
   and is explicitly registered; do not substitute Brutus's Granite 3.1 GPU
   endpoint for a Xeon CPU or Granite tools contract without a content and
   functional re-certification.
5. Private ingress, WebSockets, Console/OIDC, storage deletion, and zero-residue
   cleanup pass one seat before five and twenty-five seats are attempted.
6. Public placement remains disabled until stable DNS/TLS and the per-cluster
   public-access matrix are independently GREEN-live.

All workstation operations must use `KUBECONFIG=/explicit/path`; never switch
or rely on the default kubeconfig context.

## Flightpath promotion identity

Flightpath must not reuse Arena's remote provisioner token. Before a promotion
drill, apply `flightpath-remote-rbac.yaml` separately to Arena and Brutus using
each cluster's explicit administrative kubeconfig. Create a bound token for
`system:serviceaccount:partner-ai-launchpad:launchpad-provisioner-flightpath`,
build one kubeconfig per execution cluster, and store those encrypted
kubeconfigs only on Flightpath as:

- `partner-ai-launchpad/launchpad-arena-kubeconfig`
- `partner-ai-launchpad/launchpad-brutus-kubeconfig`

Register the same destinations with Flightpath's Argo CD using the distinct
`launchpad-argocd-manager-flightpath` token. Provisioner and Argo credentials
remain separate; neither token is reused from Arena.

During promotion, removing Arena's local provisioner binding and its Brutus
remote binding/token is the execution-cluster hard fence. Flightpath's distinct
identities are enabled only after that removal is proven. See
`docs/flightpath-dr-runbook.md` for the ordered backup, restore, activation and
failback procedure. The read-only `scripts/flightpath-dr-preflight.sh` gate must
be green before any Flightpath writer is started.
