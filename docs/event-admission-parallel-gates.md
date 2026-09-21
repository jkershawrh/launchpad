# Event admission: parallel evidence streams

This candidate advances three independent evidence components without changing
live workshops, cluster configuration, or the authoritative reservation path.
The current release state is **GREEN-local component**, not GREEN-integration or
GREEN-live.

## Stream boundaries

1. **Model-serving collector.** An opt-in local producer reads server-owned
   HTTPS targets, checks exact cluster/model identity, ready replicas, route
   reachability, and an actual inference response, then atomically writes a
   short-lived snapshot. The existing model-health reservation gate still
   fails closed when that file is absent or stale. No scheduler or target
   configuration has been installed on a cluster.
2. **Artifact cold-pull readiness.** A pure assessor compares immutable image
   digests and trusted eligible node IDs against fresh per-node pull evidence.
   It blocks missing, slow, unverified, or partial proof. The three-sample and
   180-second defaults are provisional. A trusted producer, release-manifest
   image mapping, node-set authority, and provider digest check are still
   required before admission wiring.
3. **In-flight capacity.** A pure assessor reconciles observed cluster
   allocations against active held/consumed reservations and subtracts only
   the unobserved remainder of each hold. This avoids counting consumed
   resources twice and blocks ambiguous workload ownership. A complete,
   trusted collector and transaction-safe join with the reservation ledger
   are still required.

## Convergence gate

These streams may develop independently, but admission integration is one
reviewed change. It must prove that:

- all producer contracts are supplied by trusted server-side sources;
- each snapshot is fresh, identity-bound, content-verified, and fail-closed;
- the exact image and node requirements are joined to approved catalog and
  placement evidence, not requester input;
- observed resource use, external workloads, and active holds reconcile
  without double counting or unaccounted capacity;
- the final decision is rechecked alongside the atomic reservation transaction
  so concurrent orders cannot bypass a physical-capacity failure;
- 1, 5, and 25/30-seat representative journeys pass across eligible clusters;
- cleanup returns capacity only after evidence-backed release.

Do not enable these new gates as live admission policy until their producers,
contracts, rollback behavior, and operational thresholds have integration and
live proof. Existing labs must remain undisturbed while this proof is built.
