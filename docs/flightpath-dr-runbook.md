# Flightpath promotion and disaster-recovery runbook

Flightpath is a passive, promotion-ready Launchpad control-plane target during
the September pilot. It is not an active execution cluster or a second writer.
The checked-in overlay deliberately renders every Deployment at zero replicas
and suspends every CronJob. After the pilot and three successful drills,
Flightpath becomes the primary control plane and Arena becomes the warm
control-plane standby. Arena and Brutus remain execution capacity: execution
clusters are not control-plane DR merely because they run participant labs.

## Service objectives and prerequisites

- Initial target: control-plane RPO of 5 minutes or less and RTO of 15 minutes
  or less. These objectives are not certified until backup/restore drills pass.
- Create dedicated least-privilege Launchpad service accounts for Flightpath,
  Arena, and Brutus. Store those kubeconfigs as Secrets; never use a cluster
  administrator credential in Git or in a long-running pod.
- Apply `deploy/multicluster/flightpath-remote-rbac.yaml` independently to
  Arena and Brutus. Create a short-lived bound token for
  `launchpad-provisioner-flightpath`, build one kubeconfig per cluster, and
  store them on Flightpath as `launchpad-arena-kubeconfig` and
  `launchpad-brutus-kubeconfig`. Register Arena and Brutus with Flightpath's
  Argo CD using the separate `launchpad-argocd-manager-flightpath` identity.
  Never copy either of Arena's existing remote tokens.
- Mirror the exact backend, portal, admin, public-gateway, Keycloak extension,
  and Showroom image digests to a registry reachable from Flightpath.
- Replicate the PostgreSQL database, public-access signing/encryption material,
  OAuth/OIDC client secrets, CA bundles, and cluster credential Secrets through
  an approved encrypted backup path. Git is not a secret backup system.
- Prove Flightpath can reach each managed cluster API and that its routes are
  reachable by the intended internal users before declaring the standby ready.
- Keep public access disabled for the first promotion drill. DNS, trusted TLS,
  Keycloak and external-browser certification remain a separate gate.

## Prepare the passive standby

1. Render `deploy/launchpad/overlays/flightpath-dr` and review the result. It
   must contain zero-replica Deployments and suspended CronJobs.
2. Replace every first-party image with an immutable `@sha256:` reference in a
   registry reachable from Flightpath. An execution cluster's internal
   `image-registry.openshift-image-registry.svc` address is invalid for DR.
3. Restore the encrypted Secret set through the approved secret-management
   path: database credentials, public-access signing/encryption material,
   OAuth/OIDC clients, CA bundles, and the dedicated Arena/Brutus kubeconfigs.
4. Create and bind the Flightpath PostgreSQL PVC using the certified RBD
   storage class. Start only PostgreSQL when performing a restore.
5. Run the read-only gate:

   ```sh
   scripts/flightpath-dr-preflight.sh \
     /secure/arena-admin.kubeconfig \
     /secure/flightpath-admin.kubeconfig
   ```

   The gate intentionally fails until the complete standby, Secret and image
   inputs are present. It never changes either cluster.
6. Confirm Flightpath has a healthy Argo CD/Application controller and that its
   separately registered Arena and Brutus destinations match the API URLs in
   `flightpath-clusters.yaml`. Showroom provisioning cannot fail over through
   the Launchpad database alone.

## Encrypted database backup and restore

The pilot tool writes only an encrypted artifact to the requested destination.
A permission-restricted plaintext dump exists only in a temporary directory
and is removed on every exit. Store the `.age` artifact and its checksum in
separate durable, access-controlled backup storage.

```sh
scripts/launchpad-dr-database.sh backup \
  /secure/arena-admin.kubeconfig \
  /secure/backups/launchpad-$(date -u +%Y%m%dT%H%M%SZ).dump.age \
  'age1...approved-recipient'
```

Before promotion, start only Flightpath PostgreSQL, then restore. The explicit
target confirmation and server-name check make an accidental Arena restore
fail closed:

```sh
scripts/launchpad-dr-database.sh restore \
  /secure/flightpath-admin.kubeconfig \
  /secure/backups/launchpad-TIMESTAMP.dump.age \
  /secure/backups/launchpad-TIMESTAMP.dump.age.sha256 \
  /secure/age/launchpad-dr-identity.txt \
  --confirm-target=flightpath:FLIGHTPATH_INFRASTRUCTURE_ID:DATABASE_SYSTEM_ID
```

The confirmation values come from Flightpath's immutable OpenShift
`infrastructureName` and PostgreSQL database-system identifier. The tool also
requires the exact Flightpath API URL. This manual encrypted workflow proves
restore semantics. Reaching the five minute RPO requires an approved scheduled
encrypted backup destination; do not claim that RPO from a one-time dump.

## Promotion — fence before starting a writer

1. Declare an incident and stop new orders at the public/requester edge.
2. **Fence Arena** as a control plane. Stop its backend, lifecycle workers,
   lifecycle scheduler, legacy reconciler and order ingress, or isolate their
   network.
3. Rotate or revoke Arena's credentials to every execution cluster. Remove the
   Arena-local `launchpad-provisioner-binding` before Flightpath manages Arena,
   and remove the Arena remote provisioner and Argo CD bindings/tokens on
   Brutus. Enable only the distinct `launchpad-provisioner-flightpath` and
   `launchpad-argocd-manager-flightpath` identities. This credential revocation
   is the hard split-brain fence; a database flag is not sufficient.
4. Verify there are no live Arena lifecycle leases advancing in PostgreSQL.
5. Restore the most recent verified PostgreSQL backup and required encrypted
   Secrets to Flightpath. Record the backup timestamp and resulting RPO.
6. Change Flightpath's control-plane identity to a new unique active epoch,
   enable only the cluster targets whose dedicated credentials pass probes, and
   keep public placement disabled unless public ingress is separately certified.
7. Activate in this order: PostgreSQL, backend readiness, two lifecycle
   workers, scheduler, internal portal/admin, then public gateway. Public
   gateway remains off until its own live certification passes.
8. Run reconciliation with orphan deletion disabled. Compare sessions,
   workshops, namespaces, routes, RoleBindings, Applications, and model keys.
9. Enable cleanup only after every persisted target cluster is reachable and
   the comparison has been reviewed. Resume new orders last.

Never promote Flightpath while Arena may still write. A database epoch by
itself does not prevent an isolated copy of the old database from authorizing
stale workers; credential or network fencing is mandatory.

## Validation drill

The certification drill must prove one in-flight provision and one in-flight
reclaim survive an Arena control-plane loss without changing `cluster_ref`.
Capture queue fencing tokens, session/workshop state, target namespaces,
participant URLs, cleanup output, immutable image digests, backup checksum,
audit events, and the final zero-orphan scan.

Require three consecutive successful drills. Each drill must include:

1. A fresh encrypted backup and verified checksum.
2. Arena writer and credential fencing evidence.
3. A Flightpath restore with measured RPO.
4. Read-only reconciliation before cleanup is enabled.
5. Completion of the interrupted provision and reclaim on their persisted
   target clusters.
6. A new one-seat order and successful bulk reclaim.
7. Zero remaining namespaces, Routes, RoleBindings, Argo Applications,
   entitlements, duplicate seats, or active stale lifecycle leases.
8. Failback with measured RTO and the same fence-first rules.

## Failback

Treat failback as another controlled disaster-recovery promotion. Drain new
orders, fence Flightpath, revoke its execution credentials, take and verify a
final backup, restore Arena, issue a new control-plane identity/epoch, run
read-only reconciliation, then restore workers and traffic in order. Do not run
bidirectional active/active database writers during this pilot phase.

After the September pilot, promote Flightpath permanently only when all three
drills meet the RPO/RTO objectives. Then rebuild the same zero-replica standby,
encrypted Secret set, immutable images and tested restore path on Arena. Do not
make Brutus a control-plane standby unless Launchpad and its database are
deliberately installed and maintained there.
