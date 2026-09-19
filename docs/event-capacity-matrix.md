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
idempotent and conflicting retries fail closed. Release and expiration are
idempotent states. No reservation method provisions a workshop, creates a
namespace, or changes a live cluster.

Local proof covers deterministic footprint multiplication, concurrent
overcommit rejection, evidence drift, retry behavior, release, and expiration.
A PostgreSQL integration run, API approval action, lifecycle consumption,
reconciliation, and live proof remain separate gates.

## Next boundary

The next orchestration increment may expose the ledger through an explicit
approval action and let lifecycle workers consume held allocations. It must
persist every selected cluster before provisioning and prove database-backed
reconciliation and zero-residue release before live use.
