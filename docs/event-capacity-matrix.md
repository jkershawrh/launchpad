# Event capacity certification matrix

## Decision

Event admission uses an explicit, server-owned catalog-by-cluster matrix. A
single fleet-wide seat count is not sufficient evidence that a particular lab
release can run on a particular cluster.

The v1.5 manifest makes `single_cluster_per_workshop` an explicit placement
policy. It is the safe current default, not a permanent assumption: a future
mode must be separately specified, tested, and certified before use.

Each cluster envelope declares:

- whether it is enabled for normal event placement;
- the exposure policies and capabilities it supports;
- an aggregate simultaneous certified-seat ceiling;
- an exact catalog ID and immutable release ceiling for each supported lab;
- exact certified model IDs for each cluster and required model IDs for each
  catalog release; an approved event must declare those required IDs rather
  than relying on a generic `model-endpoint` capability;
- DR-reserved and uncertified capacity as visible, non-placeable categories.

The preview treats every cohort × lab pair as one atomic workshop and applies
both catalog-cell and cluster-total constraints. A bounded deterministic search
can reroute flexible demand so that a constrained lab is not rejected by a
greedy choice, but it never splits one workshop across clusters.

The preview reports `peak_concurrent_participants` as a conservative planning
upper bound equal to the total participants. Cohort start times alone cannot
prove that retained lab use does not overlap; the current manifest has no
enforced end or reuse window. The UI labels this as an upper bound, not a
measured concurrency value. Certified model-serving capacity still needs its
own runtime and load proof before an event is admitted.

## Safety boundary

- Exact catalog release matching is mandatory.
- Public events cannot consume internal-only certification.
- Missing capabilities make that catalog/cluster cell ineligible.
- Missing exact model certification makes the cell ineligible, and a catalog's
  declared model requirements cannot be omitted from the event manifest.
- Model ID certification is a static placement requirement, not proof that a
  model replica is currently warm, exposed, responsive, or able to serve the
  expected concurrency. Reservation now also requires a separate fresh
  runtime-health snapshot for every required model on its allocated cluster.
  This is not a concurrency or load certification.
- Disabled clusters, DR-reserved capacity, and uncertified capacity never make
  an event eligible.
- A capacity preview or persisted event record does not reserve capacity,
  provision workshops, or mutate a cluster.
- Runtime resource measurements do not become certified capacity
automatically. A later provider must join approved certification evidence
and current reservations into this matrix and fail closed when either is
unavailable.

## Runtime model-serving gate

`EVENT_MODEL_HEALTH_SNAPSHOT_FILE` optionally points to a server-managed JSON
snapshot. Its document has `schema_version: "1.0"`, timezone-aware
`observed_at`, and a `models` array. Each model row identifies `cluster_id`,
`model_id`, `ready_replicas`, `route_exposed`, and `probe_success`. The provider
hashes the exact file bytes into a snapshot ID. The file must be produced by
an authorized collector; this repository does not yet deploy that collector.
The producer contract is `contracts/event-model-health-v1.yaml`.
The collector must perform fresh probes for all included rows at `observed_at`;
it must not refresh the document timestamp while carrying forward old results.

For any approved allocation with required models, missing, invalid, older than
120 seconds, future-dated beyond 30 seconds, duplicate, unready, unexposed, or
probe-failing evidence blocks new reservations. The admin forecast reports
that status and snapshot ID without creating a hold. Events with no required
models remain compatible. A configured invalid file returns 503; an absent
setting blocks only model-dependent events. This gate checks responsiveness,
not model capacity at 25/30-seat concurrency. Do not use a hand-authored or
long-lived file to claim GREEN-live.

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

Participant seat assignment is durable and atomic across backend replicas.
PostgreSQL takes ordered transaction-scoped locks for the normalized email and
workshop order, then recovers the participant identity/entitlement or assigns
the next unclaimed seat in the same transaction. Persistence errors propagate
instead of being logged and ignored, so a participant is never told a seat was
claimed when the authoritative write failed. A disposable PostgreSQL 16 run
starts two independent access-service replicas simultaneously, proves they
receive distinct seats, reconstructs a third service, and validates both
hashed browser sessions after restart.

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

Sessions issued a scoped LiteLLM key now require a persisted, secret-free
revocation receipt before cleanup can be finalized. The receipt records the
provider, stable key ID, timezone-aware confirmation time, and provider request
ID when supplied (or an explicit successful-HTTP fallback); it never stores the
raw key. Missing, malformed, or mismatched receipts keep
`model_key_revocation` nonzero. A retry after a persisted matching receipt does
not call the provider again. If the provider rejects revocation or returns no
receipt, Launchpad scrubs the raw credential and marks cleanup failed. Because
the secret is deliberately not retained, a later cleanup retry uses the unique
persisted `launchpad-<session-id>` key alias to ask LiteLLM to delete the key.
The session and reservation remain failed closed until that alias request
returns a receipt for the original stable key ID; no operator assertion can
bypass the provider confirmation.

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
ID, and succeeds on an unchanged retry after recovery. Local component proof
now covers provider-confirmed HTTP key-revocation receipts, idempotent receipt
replay, fail-closed missing-receipt behavior, and recovery by a persisted
non-secret key alias after the raw credential has been scrubbed. This does not
represent a live OpenShift cleanup, external OIDC/Keycloak browser journey, or
live LiteLLM revocation. The PostgreSQL claim proof exercises Launchpad's
identity, entitlement, seat, and hashed-session boundary; it does not certify
the external gateway or OpenShift Console SSO path.

The exact documented participant workflow is now executable as a bounded local
BDD journey at the one-, five-, 25-, and 30-seat gates. Each run starts from an
approved event record and aggregate reservation, launches the workshop through
the durable lifecycle worker, verifies every seat Ready, activates public
access, claims all seats concurrently, validates every participant session,
queues bulk reclaim, proves the old sessions are denied, and releases capacity
only after a zero-residue cleanup result. The largest run assigns 30 unique
seat references under a simultaneous claim burst.

This is GREEN-local evidence for workflow composition, not live acceptance.
The lifecycle queue and reservation ledger are local in-memory components, and
the external-resource inspection boundary is supplied an explicit zero-residue
result. It does not prove Keycloak/OIDC, browser rendering, OpenShift RBAC or
Console access, live LiteLLM revocation, Argo CD deletion, or live namespace
cleanup. Those remain required at the integration and live gates.

A second proof repeats all four seat gates against disposable PostgreSQL 16.
For each gate, the test persists the event, reservation, workshop, sessions,
access policy, identities, entitlements, hashed access sessions, lifecycle
jobs, cleanup evidence, and capacity release. It reconstructs the platform
services before checking provisioned state, uses one independent access-service
instance per participant during the claim burst, reconstructs again before
reclaim, and validates denial through another reconstructed service. The
30-seat gate assigns 30 unique seats and all 61 sessions across the four gates
survive reconstruction before being durably denied after reclaim.

That run is GREEN-integration for persistence, service reconstruction,
multi-replica claim behavior, lifecycle execution, and transactional cleanup.
It remains synthetic at the infrastructure boundary: the external resource
inspector returns an explicit zero-residue result, and neither the HTTP/browser
contracts nor OpenShift, Argo CD, LiteLLM, or Keycloak are invoked.

The FastAPI provider/consumer boundary now executes the same four seat gates
through the versioned event and public-access interfaces. It proves HTTP
reservation (`201`), asynchronous workshop launch (`202`), post-readiness code
activation (`201`), simultaneous participant claims (`200`), secure-cookie
authorization (`200`), reconciled event status (`200`), bulk reclaim (`202`),
post-reclaim denial (`403`), and cleanup finalization (`200`). Participant JSON
responses never expose the hashed-session secret; it is issued only as the
secure access cookie. The 30-request burst assigns 30 distinct seats.

Together with the separate PostgreSQL reconstruction proof, this moves CDD to
GREEN-integration. It is not a live browser or infrastructure acceptance run:
the provider is in-process, namespace RoleBinding is a component boundary, and
the external gateway, Keycloak, OpenShift, Argo CD, and LiteLLM are not called.

The first read-only Arena live preflight is intentionally RED. The permanent
`labs.smg-helix.ai` health endpoint returned `200` with trusted TLS, and OIDC
discovery returned the exact permanent issuer plus same-origin authorization
and token endpoints. The kubeconfig also names the expected Arena API server.
However, the saved Arena credential is unauthorized, so namespace read access
and the four required deployment readiness checks cannot be proven. The
preflight therefore refused to declare the target ready and changed zero
cluster resources. A refreshed scoped credential and a fully green rerun are
required before any live canary is created or activated.

## Next boundary

The next orchestration increment must exercise the external participant
claim/Keycloak SSO journey, live LiteLLM revocation, and live zero-residue
cleanup at the staged 1-, 5-, and certified-seat gates. A release remains short
of live acceptance until those external and staged proofs exist.
