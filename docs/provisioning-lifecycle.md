# Provisioning Lifecycle

This lifecycle applies after the control plane has selected a registered
execution target. Cluster creation is a separate, slower fleet-capacity
lifecycle; ordinary orders consume certified warm capacity rather than
creating a new cluster per lab.

## Order admission and placement

Before the first session enters `provisioning`, Launchpad must:

1. resolve the catalog's deployment class (`shared_namespace`,
   `dedicated_workshop_cluster`, or exceptional `dedicated_seat_cluster`);
2. filter registered targets by credentials, API/Operator health, hardware,
   OpenShift version, storage, ingress, network policy, required model, and
   immutable image/content availability;
3. verify the published catalog × cluster × exposure-policy seat ceiling;
4. reserve the whole workshop's steady, bounded-transient, shared-service,
   model, route, and pod capacity;
5. persist the selected `cluster_ref`, placement explanation, catalog version,
   content version, image digests, and reservation; and
6. revalidate immediately before resource creation.

If one target cannot fit the complete workshop, admission fails. The first
release never silently splits seats across clusters. Provisioning, validation,
expiration, reclaim, and orphan cleanup always use the persisted target and
never retry against a different cluster.

## Session States

| State | Meaning |
|-------|---------|
| `requested` | Session created, not yet provisioned |
| `provisioning` | Namespace, quota, apps being deployed |
| `validating` | Provisioning complete, validation checks running |
| `ready` | All validation passed, lab URL available |
| `active` | User has opened/activated the lab |
| `expired` | TTL exceeded |
| `resetting` | Environment being torn down for reuse |
| `reclaimed` | All resources released, session archived |

## Failure States

| State | Meaning | Recovery |
|-------|---------|----------|
| `rejected` | Request failed constraint evaluation | Submit new request |
| `failed` | Provisioning error (namespace, deploy, etc.) | Reclaim and retry |
| `validation_failed` | One or more checks returned `fail` | Reclaim and retry |
| `cleanup_failed` | Reset could not fully clean up | Force reclaim via admin |

## Transition Rules

15 valid transitions:

```
requested       -> provisioning
provisioning    -> validating
provisioning    -> failed
validating      -> ready            (requires: all validation results present, none failed)
validating      -> validation_failed
ready           -> active
active          -> expired
active          -> resetting
expired         -> resetting
expired         -> reclaimed
resetting       -> reclaimed
resetting       -> cleanup_failed
failed          -> reclaimed
validation_failed -> reclaimed
cleanup_failed  -> reclaimed
```

All other transitions raise `InvalidTransitionError`. The lifecycle module enforces these rules as deterministic functions — no implicit state changes.

### Validation Gate

The transition from `validating` to `ready` has an extra guard:
1. `validation_results` must not be empty.
2. No result may have `result: fail`.

If either condition is violated, `ValidationRequiredError` is raised. This prevents labs from being marked ready without proof.

## Per-Session MaaS Key Tracking

Each provisioned session receives a unique MaaS API key (`sk-launchpad-{uuid}`). This key:
- Scopes model access to the session
- Enables per-session token/request tracking in showback
- Is included in the handoff package for the user
- Is revoked when the session is reclaimed

Model serving is normally a shared private service, not a model pod loaded in
every participant namespace. Model availability, readiness, queue pressure,
latency, and scoped-key issuance are functional readiness inputs. A lab that
teaches model deployment may explicitly declare a different contract.

## Lifecycle Events

Every state transition is recorded as a `LifecycleEvent` with:
- `from_status` and `to_status`
- Timestamp
- Reason (human-readable)

The full event log is stored on the session and available via the API. Timestamps for `started_at` (first activation) and `completed_at` (reclaim) are set automatically by the transition function.

## Intelligence Integration Points

The intelligence layer integrates at two points in the lifecycle:

**Before provisioning** (`_resolve_hardware` + `_get_placement_recommendation`):
- `OrchestrationBrain.decide()` classifies the workload, selects hardware, recommends a cluster
- The `OrchestrationDecision` is stored in `session.resources["decision"]`
- If the brain is unavailable, falls back to static hardware selection

**After validation** (`_record_feedback`):
- `FeedbackTracker.record_outcome()` records success/failure, latency, cluster, hardware
- Outcome is persisted to PostgreSQL (`provisioning_outcomes` table)
- Future provisioning decisions use this history to avoid failing combinations

## Fleet-capacity lifecycle

The capacity manager operates independently of an interactive lab order:

```text
forecast demand -> allocate/provision cluster -> register identity
-> install baseline -> verify ingress/storage/registry/models/observability
-> certify catalog pairings -> mark placement eligible
-> reserve and consume capacity -> drain -> verify no ownership
-> return to warm pool or retire
```

Scheduled events reserve clusters and pre-pull signed release digests before
participant access opens. A cluster may be disabled for new placement while
its active sessions continue. Active sessions are not migrated; their reclaim
continues against the recorded cluster.

## Artifact readiness

Each generated workload references a signed immutable digest from the approved
HA registry or an explicitly synchronized mirror. Readiness requires the exact
digest to be reachable and trusted from eligible worker pools. A mutable tag,
an ImageStream that points to a missing manifest, or another execution
cluster's internal registry cannot satisfy the production contract.

Image pull success alone is not lab readiness. Launchpad still runs application,
Showroom, terminal, authorization, model, and documented-workflow probes.
