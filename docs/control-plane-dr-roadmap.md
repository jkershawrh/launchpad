# Launchpad control-plane disaster-recovery roadmap

## Decision and boundary

Arena remains the active pilot control plane until the retained September 17
workshops close and the migration gate is explicitly approved. Flightpath is
now the selected durable transitional control-plane home. Arena becomes the
rollback/standby site after cutover and may remain execution capacity only when
its execution health is independently certified.

This selection does not declare the cutover complete and does not permit two
active writers. Flightpath must not assume the production database, public
edge, identity issuer, GitOps ownership, ordering, or cleanup authority until
Arena has been hard-fenced and the backup, restore, reconciliation, rollback,
and public-access gates pass. The isolated `launchpad-flightpath-candidate`
writer uses its own database and no public ingress; it cannot mutate the Arena
control plane's retained workshop records.

Flightpath is a transition architecture, not the final production home.
Production moves the same pattern to a dedicated production control-plane
cluster with a separate recovery failure domain. Arena, Brutus, Flightpath
execution capacity, and future clusters remain replaceable execution targets.

The recovery design also separates the shared AI-serving and artifact-supply
planes. A control-plane promotion must recover model-routing policy, scoped-key
authority, approved registry credentials, catalog digests, and mirror state,
but it does not move active model pods or participant namespaces. Execution
and AI clusters remain registered targets; the restored control plane resumes
authority using persisted `cluster_ref` and immutable artifact references.

The architecture permits no active/active writers. Exactly one control plane
may accept orders, mutate lifecycle state, manage Launchpad Argo CD
Applications, issue entitlements, or reclaim resources. Database roles and
epochs provide application safety, but revoking credentials or isolating the
old site is the hard split-brain fence.

The initial service objectives are a five-minute RPO and a 15-minute RTO. The
objectives remain targets—not claims—until the scheduled backup path and three
complete failover/failback drills meet them.

## Current proof and current exposure

As of September 14, the passive Flightpath foundation is GREEN-live:

- a fresh encrypted Arena database backup restored to Flightpath in 12 seconds;
- 18 application tables and 19,795 rows matched exactly;
- Flightpath runs an Available but empty OpenShift GitOps controller;
- dedicated, least-privilege Arena and Brutus provisioner and Argo CD
  identities are registered on Flightpath;
- every Flightpath Launchpad Deployment is at zero and every Launchpad CronJob
  is suspended;
- the passive preflight passes without starting a writer or changing an active
  participant resource.

The following remain RED and prevent a DR claim:

- the backup is a manual point-in-time artifact, not a scheduled encrypted
  backup meeting the five-minute RPO;
- Arena has not been hard-fenced and Flightpath has not been promoted;
- no in-flight provision or in-flight reclaim has survived a site promotion;
- public edge cutover, OIDC recovery, and identity reauthentication have not
  been proven on Flightpath;
- Argo CD ownership of existing Launchpad Applications has not been transferred
  between control planes;
- failback has not been executed;
- the complete exercise has not passed three consecutive drills;
- the current Arena backend, PostgreSQL, lifecycle worker, and public tunnel
  each have only one Ready replica while `gnr2` is unavailable. That is a pilot
  availability risk, not a completed HA topology.

On September 23, an isolated Flightpath candidate first proved scheduled TTL
reclamation for `intel-llm-cpu-serving`, which exposed an aware-versus-naive
timestamp comparison defect. The fix was then built into immutable backend
image digest `sha256:2bd7996ed013f2138c85c4922aee4610a1019d0f5929dc5f4a4580db04f5fc71`
and deployed only to the candidate namespace. Candidate 03 subsequently
provisioned one ready internal seat for each pilot catalog, returned HTTP 200
from all three Showrooms, passed every declared pod and route validation, and
completed live calls through both registered candidate models. A real
five-minute scheduler cycle accepted timezone-aware expiration values,
reclaimed all three workshop orders without a manual reclaim call, scrubbed
their MaaS keys and service-account tokens, and left zero namespaces or labeled
resources. This closes the internal three-catalog lifecycle component gate. It
does not certify public access, participant browser journeys, production-shaped
load, database recovery, control-plane migration, HA, or DR.

## Incident decision tree

Use the smallest recovery action that matches the failed boundary.

### Application process incident

A backend, lifecycle-worker, gateway, or GitOps controller pod fails while its
cluster, database, and at least one eligible node remain healthy. Kubernetes
reschedules it and the durable lifecycle lease transfers to another worker.
Flightpath is not promoted.

### Execution-worker incident

An Arena or Brutus worker becomes NotReady or Unknown while the Launchpad
control plane is usable. Disable that worker or cluster for new placement,
recover existing workloads from stable labels and storage, and validate routes,
models, terminals, and Showroom. An execution-worker incident does not promote
Flightpath. The September 14 recovery also shows why catalog workloads must use
certified worker-pool labels or soft placement constraints rather than a dead
hostname selector.

### Execution-cluster incident

One execution cluster is unavailable but the Arena control plane is healthy.
Stop placement to that cluster, preserve every persisted `cluster_ref`, keep
other clusters serving, and do not retry cleanup or migrate an active workshop
elsewhere. Flightpath is not promoted.

### Control-plane dependency incident

Arena loses one stateful dependency but the cluster remains controllable.
Freeze new orders, recover the dependency locally, verify the database and
queue, and resume only after end-to-end readiness. Do not invoke site DR merely
to work around a repairable singleton pod.

### Control-plane incident

Arena cannot safely provide or recover the database, lifecycle authority,
identity, or order path inside the 15-minute objective. Declare DR, stop
admission, hard-fence Arena, restore the latest verified recovery point, and
promote Flightpath. A tunnel-only or browser-only symptom is not sufficient;
the incident commander must confirm the transaction path has failed.

## Recovery-state contract

The recovery set is versioned as one release and restored before promotion:

1. **Lifecycle data:** PostgreSQL catalog, tenant, order, workshop, seat,
   reservation, `cluster_ref`, public access, entitlement, audit, lifecycle job,
   lease, and fencing state.
2. **Secret bundle:** database credentials, application signing/encryption
   material, OAuth/OIDC clients, cookie keys, Keycloak bootstrap/configuration
   inputs, CA bundles, registry pull credentials, and dedicated execution
   cluster credentials. Secret values stay in an approved encrypted store and
   never in Git or evidence.
3. **Immutable release:** exact Git revision, database migration level, image
   digests, catalog/content versions, policy versions, and rendered manifests.
4. **GitOps ownership:** the list of Launchpad-owned Applications, their
   destination clusters/namespaces, source revisions, health, and current
   controller identity. Promotion must perform a GitOps ownership transfer;
   Flightpath may regenerate only the Applications represented by restored
   lifecycle state.
5. **Public and internal edge:** stable hostnames, DNS/tunnel target, trusted
   TLS, route policy, WAF policy, and an identity-provider issuer that resolves
   consistently from browsers and control-plane services.
6. **Evidence:** encrypted backup checksum, source commit, image digests,
   timestamps, RPO/RTO clock, fence evidence, state comparison, probes, audit
   events, and cleanup results.

An incomplete or mismatched recovery set fails closed. A successful database
restore alone is not permission to start a writer.

## Delivery phases

### Phase 0 — event-safe pilot baseline

Complete before September 17 without a live site cutover:

- keep Flightpath passive and run the read-only preflight daily;
- take and verify an encrypted backup before each workshop order/reclaim cycle
  and immediately before the event freeze;
- renew Flightpath's Arena and Brutus provisioner and Argo credentials before
  they enter a 24-hour expiry window;
- mirror the exact release digests to the recovery-reachable registry;
- record the current namespace, Application, RoleBinding, Route, entitlement,
  lifecycle-job, and lease inventory;
- prove local Arena recovery of backend, PostgreSQL, GitOps, and the named
  tunnel without changing participant state;
- retain the internal requester/admin path as the event fallback and publish a
  manual incident/reclaim path.

Exit gate: event workloads can run and be reclaimed on their persisted targets,
one current encrypted recovery point is verified, and Flightpath preflight is
GREEN. This phase does not award DR certification.

### Phase 1 — automated recovery points and standby currency

- write a scheduled encrypted backup to durable object storage outside Arena;
- create a checksum, immutable evidence manifest, and source database marker
  for every recovery point;
- automatically verify decryptability and `pg_restore --list`; restore the
  newest artifact to an isolated verification database on a schedule;
- export the secret bundle through the approved secrets manager using versioned
  references, not copied developer credentials;
- alert on backup age greater than five minutes, failed verification, secret
  version drift, migration drift, expired execution credentials, missing image
  digests, and failed Flightpath preflight;
- define retention and deletion: frequent short-term recovery points, daily and
  event-boundary checkpoints, and a separately protected last-known-good copy.

Exit gate: the measured age of the newest verified recovery point satisfies the
five-minute RPO for seven days, including one isolated restore per day.

### Phase 2 — deterministic fence and promotion tooling

- implement a dry-run-first promotion command that captures state before any
  mutation and requires an incident ID plus an exact source/target confirmation;
- close requester and public order admission while allowing read-only status;
- scale Arena backend/lifecycle/scheduler/reconciler writers to zero;
- revoke Arena's provisioner and Argo identities on every execution cluster and
  prove denied mutations. If Arena cannot be reached, apply a network fence and
  revoke its remote credentials from the target clusters;
- stop or isolate Arena's Launchpad Application ownership before Flightpath can
  create or adopt any Application;
- restore the newest verified data and secret bundle to Flightpath;
- set a unique Flightpath control-plane ID/epoch and enable only execution
  targets whose credentials, APIs, ingress, storage, images, and models pass;
- activate PostgreSQL, backend readiness, lifecycle workers, scheduler,
  requester/admin, then the participant gateway;
- run read-only reconciliation first and require an operator-approved diff
  before enabling cleanup or new orders.

Exit gate: automated evidence proves the hard split-brain fence, exactly one
active writer epoch, successful health gates, and a reversible stop point before
traffic moves.

### Phase 3 — identity, GitOps, and public edge recovery

- deploy the same public gateway and Keycloak realm/client configuration to
  Flightpath from immutable configuration and restored secrets;
- preserve participant identities and entitlements in PostgreSQL. Existing
  browser sessions may be invalidated; identity reauthentication with the same
  lab URL, email label, and instructor code is the pilot recovery contract;
- prove code hash, rotation version, TTL, entitlement, and namespace
  RoleBinding behavior after restore;
- implement GitOps ownership transfer using the restored Application inventory.
  Never let Arena and Flightpath reconcile the same Launchpad Application;
- prepare a Flightpath public origin/tunnel and an API-scoped public edge
  cutover for `labs.smg-helix.ai`. Keep one stable participant hostname; do not
  expose per-cluster control-plane hostnames;
- validate trusted TLS, issuer/callback URLs, gateway cookies, Showroom,
  terminal WebSockets, proxied tools, logout, resume, and cross-seat denial;
- define the reverse public edge cutover before activating the forward change.

Exit gate: one external participant reauthenticates, resumes the original seat,
uses every required tool, and remains scoped to the original namespace after a
controlled public edge cutover and rollback.

### Phase 4 — complete failover and failback certification

Run only in an approved window with disposable certification orders:

1. create one ready seat, one in-flight provision, and one in-flight reclaim;
2. capture the newest verified backup and start the RPO/RTO clock;
3. hard-fence Arena and promote Flightpath through Phases 2 and 3;
4. complete the in-flight provision and in-flight reclaim without changing
   either persisted target cluster;
5. create and use a new public one-seat order through Flightpath;
6. reclaim all certification resources and prove zero residue;
7. fail back by freezing admission, hard-fencing Flightpath, taking a final
   backup, restoring Arena, issuing a new epoch, transferring GitOps and edge
   ownership, and reconciling read-only before writes resume;
8. publish the evidence manifest and measured RPO/RTO.

The run fails for duplicate writers, stale credentials that can still mutate,
data/count mismatch, changed `cluster_ref`, duplicate seats, invalid public
authorization, failed tool routes, or non-zero residue. Repeat the full sequence
as three consecutive drills; any defect resets the sequence after its RED test
and fix.

Exit gate: three consecutive drills meet the five-minute RPO and 15-minute RTO,
including public access, in-flight lifecycle recovery, failback, and zero
residue.

### Phase 5 — transitional primary and production migration

After the event and the Phase 4 gate, Flightpath becomes the transitional
primary control plane. Arena becomes its warm standby and remains an execution
cluster only when its execution capacity is separately healthy. Repeat the
standby preflight, recovery-point, secret, registry, identity, GitOps, edge, and
drill controls in the reverse direction.

The final production destination is a dedicated control-plane cluster with:

- stateless API, portal, admin, gateway, and lifecycle-worker replicas spread
  across certified failure domains;
- an approved highly available PostgreSQL implementation plus encrypted
  off-site recovery points;
- durable object storage for backups and evidence;
- an approved secrets manager and short-lived, automatically renewed remote
  identities;
- highly available GitOps with per-cluster least-privilege credentials;
- stable managed DNS, TLS, WAF, identity-aware ingress, and tested origin
  failover;
- centralized metrics, logs, traces, audit, alerting, and incident ownership;
- a warm standby in a separate recovery failure domain.

The production design retains the fence-first active/passive site contract even
when services and PostgreSQL are highly available inside each site.

## Certification and evidence matrix

Every drill records these independent GREEN/RED results:

- **Data:** recovery-point age, checksum, decryptability, restore duration,
  migration level, table counts, row counts, and lifecycle queue/lease state.
- **Fence:** old API admission closed, old writers stopped, old provisioner and
  GitOps identities denied, and exactly one active epoch.
- **Runtime:** backend readiness, lifecycle workers, scheduler, PostgreSQL,
  GitOps, registry pulls, execution APIs, storage, models, and routes.
- **Lifecycle:** one in-flight provision, one in-flight reclaim, a new order,
  persisted target retention, idempotency, TTL, and zero residue.
- **Access:** DNS/TLS, OIDC, identity reauthentication, claim/resume, Showroom,
  terminal WebSockets, proxied tools, logout, expiry, and cross-seat denial.
- **GitOps:** explicit old-controller fence, restored Application inventory,
  one owner per Application, health, pruning, and no orphan Applications.
- **Operations:** alert delivery, incident ID, named decision owner, timestamps,
  operator approvals, RPO, RTO, rollback/failback, and evidence hashes.

TDD requires each discovered defect to become a failing regression test before
the repair. CDD versions the backup, fence, promotion, identity, GitOps, and
edge interfaces. BDD runs the operator and participant journeys. Component
tests isolate backup/restore, credentials, public routing, identity, queue, and
GitOps ownership. EDD stores credential-free immutable receipts. A release may
advance only when the red/green matrix and 100-point DR rubric agree.

## Stop conditions and authority

Promotion stops before Flightpath writers start if the old control plane cannot
be fenced, the newest verified backup is outside the accepted RPO, the secret
bundle or image digests are incomplete, migrations differ, the database compare
fails, or required execution targets cannot be authenticated. After writers
start, promotion stops before public traffic or cleanup if identity, GitOps
ownership, route, authorization, or read-only reconciliation differs from the
recorded source state.

The incident commander authorizes failover and failback. A platform operator
executes the runbook; a second operator verifies the fence and state diff; the
security owner approves credential and public-edge changes; the workshop owner
decides whether participant service resumes. Break-glass actions are bounded,
time-limited, audited, and reconciled back to Git.

No full promotion drill runs while non-disposable workshops are active unless
an actual declared incident makes recovery necessary. This protects current
participants while keeping the roadmap executable rather than aspirational.

## Source artifacts

- `deploy/launchpad/overlays/flightpath-dr`: fail-closed passive runtime
- `deploy/launchpad/overlays/flightpath-dr-gitops`: passive GitOps prerequisite
- `deploy/multicluster/flightpath-remote-rbac.yaml`: distinct remote identities
- `scripts/flightpath-dr-preflight.sh`: read-only standby gate
- `scripts/launchpad-dr-database.sh`: encrypted backup/verification/restore
- `docs/flightpath-dr-runbook.md`: operator procedure
- `docs/ha-dr-certification-20260908.md`: red/green matrix and rubric
- `evidence/runs/flightpath-passive-dr-20260914.json`: passive restore receipt
