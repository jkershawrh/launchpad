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
5. Use the optional pure `ReservationGuard` seam after active holds are read
   under the in-memory lock or PostgreSQL serializable transaction and
   per-cluster advisory locks, before insertion. Local concurrency tests prove
   that two orders cannot both consume one physical headroom envelope when
   a trusted snapshot is supplied. This seam is not enabled by the API and
   must not perform network I/O while the database transaction is open.
6. Prove concurrent orders, failure injection, replay, rollback, cleanup,
   and 1/5/25/30-seat representative journeys before live enablement.

All work in this slice was local. No active workshop, execution cluster, or
public route was changed.

## Trusted-input progress and current blockers

- The promoted-release adapter can authenticate exact immutable image manifests
  and receipts, but the checked-in registry policy is provisional and therefore
  authorizes no release. A trusted promotion producer, approved registry owner,
  signing identity, and pull grants are still required.
- The eligible-node adapter can read an explicitly selected cluster through
  its configured client and apply a complete, promoted placement policy, but
  no authoritative producer for every release's scheduler constraints is yet
  connected. No live node inventory was read in this slice.
- The in-flight collector can publish a strict private snapshot only from a
  complete inventory and exact reservation/workshop/seat identities. The
  current platform does not consistently label live seat namespaces with all
  of those IDs. A local read-only Kubernetes observer now handles complete
  paginated inventory and effective pod requests, but its model-slot source,
  scoped service account, persisted-workshop adapter, attestation, and live
  proof are absent. The CLI therefore exits without writing a snapshot. New
  labels apply to future orders only; existing workshops remain untouched.
- The guard seam is optional and has no effect on current orders. It is not
  yet supplied by the API because these producer and identity proofs are open.
