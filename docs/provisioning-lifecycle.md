# Provisioning Lifecycle

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
