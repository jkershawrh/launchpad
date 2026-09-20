# Event capacity certification matrix

## Decision

Event admission uses an explicit, server-owned catalog-by-cluster matrix. A
single fleet-wide seat count is not sufficient evidence that a particular lab
release can run on a particular cluster.

The v1.4 manifest makes `single_cluster_per_workshop` an explicit placement
policy. It is the safe current default, not a permanent assumption: a future
mode must be separately specified, tested, and certified before use.

Each cluster envelope declares:

- whether it is enabled for normal event placement;
- the exposure policies and capabilities it supports;
- an aggregate simultaneous certified-seat ceiling;
- an exact catalog ID and immutable release ceiling for each supported lab;
- DR-reserved and uncertified capacity as visible, non-placeable categories.

The preview treats every cohort × lab pair as one atomic workshop and applies
both catalog-cell and cluster-total constraints. A bounded deterministic search
can reroute flexible demand so that a constrained lab is not rejected by a
greedy choice, but it never splits one workshop across clusters.

## Safety boundary

- Exact catalog release matching is mandatory.
- Public events cannot consume internal-only certification.
- Missing capabilities make that catalog/cluster cell ineligible.
- Disabled clusters, DR-reserved capacity, and uncertified capacity never make
  an event eligible.
- A capacity preview or persisted event record does not reserve capacity,
  provision workshops, or mutate a cluster.
- Runtime resource measurements do not become certified capacity
  automatically. A later provider must join approved certification evidence
  and current reservations into this matrix and fail closed when either is
  unavailable.

## Provider contract

Set `EVENT_CAPACITY_MATRIX_FILE` to a server-controlled YAML document matching
`EventCapacityMatrixDocument` in `contracts/event-manifest-v1.yaml`. The
document requires a schema version, immutable matrix ID, two distinct
approvers, a timezone-aware approval timestamp, evidence references, and the
cluster envelopes. Launchpad computes the SHA-256 digest of the exact source
bytes and persists that digest with the preview and event decision.

When the setting is absent, previews report matrix `unconfigured` and zero
placeable capacity. When the setting is present but the document is missing or
invalid, the API returns `503` and does not persist an event. Matrix contents
are never accepted from the participant or requester payload.

Before reservation, the matrix must be intersected with a fresh ACM placement
snapshot. The resulting decision records both the matrix ID/digest and ACM
snapshot ID/time. ACM can only disable matrix entries; it cannot create
certified capacity.

Every catalog/release cell also declares a server-owned per-seat resource
footprint. Every cluster declares the certified aggregate envelope for seats,
CPU millicores, memory MiB, pod slots, storage GiB, routes, and model slots.
An absent all-zero catalog footprint fails closed at reservation time rather
than silently reserving seats without their operational cost.

## Transactional reservation boundary

`EventReservationLedger` converts each approved cohort/lab allocation into one
atomic hold on its persisted `cluster_ref`. A plan records the exact matrix
ID/digest and ACM snapshot digest used by the approved preview. Reservation
rejects changed evidence, a stale fleet snapshot, disabled targets, incomplete
resource footprints, or any aggregate or catalog-release overcommit.

The PostgreSQL store runs at `SERIALIZABLE` isolation and takes sorted
per-cluster advisory transaction locks before reading active holds and writing
the whole plan. The natural event/cohort/lab key makes identical retries
idempotent and conflicting retries fail closed. Expiration marks a hold stale
but does **not** return its capacity to the pool: both `held` and `expired`
records remain capacity-consuming until cleanup has produced a non-empty
evidence identifier. Cleanup-evidenced release is idempotent, while a later
release carrying different evidence fails closed. This prevents an expired
database timer from authorizing overcommit while namespaces, routes, model
keys, or other resources may still exist.

The admin-only reservation API re-reads the immutable approved event, rebuilds
the plan against the current matrix and fresh ACM snapshot, and persists every
selected `cluster_ref` before any lifecycle work is allowed. Its paired release
API accepts only `cleanup_completed: true` plus cleanup evidence. No reservation
method provisions a workshop, creates a namespace, or changes a live cluster.

Lifecycle consumption is a separate one-to-one transition. It binds a held
reservation to a deterministic workshop ID only when event, catalog ID,
immutable catalog release, seat count, and `cluster_ref` exactly match. The
transition is serialized per reservation and identical retries are idempotent;
a different workshop, an expired/released hold, or any changed input fails
closed. Consumed reservations remain capacity-consuming until cleanup-evidenced
release.

Reserved workshop creation records the reservation, event, cohort, lab,
release, seat count, and cluster on the order. Immediately before provisioning,
the lifecycle service re-reads the reservation and rejects catalog drift,
cluster movement, seat-count changes, or a missing/incorrect workshop binding.
Local lifecycle proof provisions all 30 synthetic seats on the persisted target
without recalculating placement.

Local proof covers deterministic footprint multiplication, concurrent
overcommit rejection, evidence drift, retry behavior, admin authorization,
persisted cluster assignment, cleanup-evidenced release, and fail-closed
expiration. It also covers deterministic workshop consumption, tamper rejection,
and a 30-seat synthetic lifecycle run on the persisted cluster.

The event launch API now reads the complete event reservation set, compares it
to every immutable cohort/lab allocation, creates deterministic workshop orders,
and queues one stable lifecycle job for each order. It never provisions inside
the API request. An identical retry returns the same workshops and jobs. A
locally injected failure after the first job proves that a subsequent retry
finishes the event without duplicating either workshops or lifecycle jobs.
Public workshops remain explicitly `pending_activation`; instructor codes are
issued only after readiness so a failed event request cannot lose a one-time
secret.

Public activation is a separate admin-only, single-workshop action. It requires
the workshop and every reserved seat to be ready, verifies that every seat has
a session on the persisted cluster with a finite expiration, and uses the
earliest seat expiration for the access policy. The response returns the
public URL and instructor code once; only the Argon2id hash is retained. A
repeat activation fails closed and directs the operator to the existing code
rotation workflow. Activating one workshop at a time prevents a later failure
from discarding codes already created for other workshops.

The admin-only event status API is the read-only reconciliation boundary for
operations. It joins the immutable allocation plan to every reservation,
deterministic workshop, lifecycle job, seat state, persisted cluster, and
public-access policy. It reports whether the reservation plan is complete and
derives an event state of reserved, progressing, awaiting public access, ready,
cleanup-evidence pending, released, or attention required. The response may
include an already-issued public URL, but its schema cannot include or
redisplay the one-time instructor code. Missing reservations, failed jobs,
failed workshops, and failed seats surface as attention required without
mutating any lifecycle resource.

The admin-only event reclaim action requires the complete immutable reservation
plan and verifies every consumed reservation-to-workshop binding before making
any change. For public events it disables all workshop access policies first,
then queues one stable, bounded reclaim job per workshop on the reservation's
persisted cluster. Identical retries reuse the same jobs, and a missing
reservation fails before access is changed. The action does not release held
capacity; release remains a separate cleanup-evidenced transition.

Cleanup finalization is a separate admin-only proof gate. It requires every
cluster-bound reclaim job to have succeeded, every workshop to be completed,
every seat and persisted session to be reclaimed, and all stored credentials
to be scrubbed. For OpenShift sessions it performs read-only checks for the
seat namespace, the control-namespace image-puller RoleBinding, and the
deterministic Showroom and workload Argo CD Applications. It also verifies the
public policy is disabled, no active or reauthentication entitlement remains,
and any identity with no other active lab has been disabled. Any unavailable
probe, incomplete record, or nonzero count fails closed.

The exact sorted evidence payload is hashed with SHA-256. That evidence ID is
persisted on every released reservation, making retries idempotent and causing
changed cleanup evidence to fail closed. The result exposes only counts,
resource identifiers, and the digest; it contains no instructor code,
participant email, access token, or model credential.

A disposable PostgreSQL 16 integration run now proves a two-seat public event
across the approved manifest, reservation ledger, workshop/session stores,
public-access store, and lifecycle-job store. The run claims one seat, queues
and executes reclaim, reconstructs every service from PostgreSQL, finalizes
cleanup, reconstructs the services a second time, and verifies that the same
evidence digest returns an idempotent zero-release replay. A second run starts
two reconstructed finalizers concurrently and proves that PostgreSQL releases
the reservation exactly once while both callers converge on the same digest.
This is integration evidence for persistence, process restart, and concurrent
finalization. A PostgreSQL trigger fault also proves that a rejected release
transaction rolls back fully, keeps reservations consumed without an evidence
ID, and succeeds on an unchanged retry after recovery. This does not represent
a live OpenShift cleanup, external OIDC browser journey, or model-key
revocation receipt.

## Next boundary

The next orchestration increment must exercise participant claim/SSO,
model-key revocation evidence, and live zero-residue cleanup at the staged 1-,
5-, and certified-seat gates. A release remains short of live acceptance until
those external and staged proofs exist.
