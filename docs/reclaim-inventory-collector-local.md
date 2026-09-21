# Read-only reclaim inventory collector seam

`backend/app/services/reclaim_inventory_collector.py` is a pure normalizer for
the [reclaim-readiness/v1 contract](reclaim-readiness-local-contract.md). It
does not contain a database, Kubernetes, or HTTP client and has no write path.
Tests inject a fake provider. No live collector is configured or certified.

An eventual read-only provider must return `CollectionBatch(rows, complete,
observed_at)` from five methods: the **complete** retained-workshop roster,
the **complete** registered execution-cluster roster, sessions for those
workshops, reservations for those workshops, and all Launchpad-managed
namespace ownership observations on **each registered cluster**. The
namespace scan must be independently scoped to its requested cluster; it
must not substitute a cached observation from another cluster. `complete`
must be backed by pagination/exhaustion evidence, not simply asserted.

The normalizer requires a fresh timestamp on every batch, rejects missing
cluster observations, projects only fields in the v1 inventory contract, and
passes the result through the existing balance validator. It checks snapshot
freshness again at collection completion so a slow scan cannot silently age
out. It scans every
registered cluster so a namespace bearing an in-scope workshop/session ID on
the wrong cluster is not missed. It intentionally excludes unrelated managed
namespaces from the narrow balance contract; those still belong in the broader
T-30 inventory and orphan audit. No email, instructor code, token, or
credential fields enter the normalized result or exception text.

## Boundaries before Tuesday's reclaim

- A provider's claim that its roster is complete is **not independent proof**.
  An omitted workshop or cluster can still be invisible if the authority
  itself is wrong. Review provider queries, pagination, source identity, and
  independent counts before trusting a snapshot.
- The collector makes separate observations, not one atomic cross-cluster
  transaction. Its oldest observation is the normalized `captured_at` time;
  inventory drift between reads needs a fresh, independent T-30 check.
- The narrow validator does not observe entitlements, claims, Routes,
  Applications, PVCs, RoleBindings, model keys, active jobs, or audit cursors.
- `ready: true` means only that the supplied records balance. It is neither
  reclaim authorization nor lifecycle/zero-residue certification. No live
  reclaim or deployment was performed while adding this seam.
