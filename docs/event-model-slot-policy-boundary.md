# Promoted model-slot policy boundary (local only)

The file-backed model-slot observer now requires a separately configured SHA-256
digest for one immutable, promoted model-concurrency policy. The policy names
the exact cluster, model ID, model release, certified concurrency ceiling,
approval time, and two distinct approvers. Its exact bytes must match the
out-of-band digest. The observation must name that same policy ID and digest,
cluster, model, and release; it must be fresh, follow promotion, and report
slots no higher than the policy ceiling. Explicit zero is valid. Legacy v1.0
observations and a free-form `capacity_policy_ref` fail closed.

The digest must come from a reviewed release configuration or independent
approval process, **not** from the observation or the policy file itself. The
approver fields are trace metadata, not a cryptographic signature. Pinning a
digest produced by the same untrusted source would void this trust boundary.

This is a local proof of matching evidence, not proof that the serving system
currently has that many available slots. The real producer, policy promotion
and revocation process, per-model runtime accounting, model-route health,
cluster integration, and admission wiring remain open. Nothing here enables
orders, changes a live cluster, or certifies the existing pilot labs.
The downstream `ModelSlotObservation` currently carries only a cluster ID and
aggregate slot count, not model ID or release. It must not be used for
multi-model admission until that identity is preserved end to end and
per-model capacity is reconciled without double counting.
The downstream `ModelSlotObservation` currently exposes only cluster and slot
count; it drops model/release identity. It therefore cannot be used as a
multi-model admission supply until that identity is preserved end to end.
