# Event admission convergence: local rehearsal

`assess_event_admission_with_sources` is a read-only composition of certified
capacity, active holds, model serving, trusted release images and eligible
nodes, observed cold pulls, and in-flight physical headroom. Its contract is
`contracts/event-admission-convergence-v1.yaml`.

The local tests prove that complete fresh evidence permits a candidate and
that absent model, artifact, placement, or physical-capacity evidence blocks.
They also prove that an existing hold is not treated as a second candidate.
The function creates no reservation and is **not connected to the event API**.

Before wiring it into authoritative admission:

1. Authenticate the promoted release source and verify its promotion evidence
   against the exact immutable catalog release. Enumerate every runtime image.
2. Obtain current eligible nodes from scheduler-aware cluster inventory. New
   and replaced nodes must invalidate stale cold-pull proof.
3. Deploy trusted cold-pull and in-flight collectors. A file digest verifies
   bytes, not producer identity or completeness; their service accounts,
   source attestations, clocks, and failure behavior require certification.
4. Define the in-flight model-slot accounting domain, especially for remote
   inference endpoints. Reconcile observed use against persisted held and
   consumed reservations without double counting.
5. Recheck the joined decision inside or immediately adjacent to the
   serializable capacity-reservation boundary. A read-only result can become
   stale between evaluation and commit and must never be treated as an
   admission token.
6. Prove concurrent orders, failure injection, replay, rollback, cleanup,
   and 1/5/25/30-seat representative journeys before live enablement.

All work in this slice was local. No active workshop, execution cluster, or
public route was changed.
