# Read-only reclaim source boundary (local proof)

`PaginatedReclaimSource` adapts a supplied page provider to the existing
`build_reclaim_inventory` collector. It creates no database, Kubernetes, HTTP,
or deletion client and grants no reclaim authority.

## Provider contract

The provider implements `fetch_page(collection, cursor, workshop_ids,
cluster_ref, expected_revision)` and returns an `InventoryPage` with rows,
source identity, snapshot revision, requested-cursor echo, next cursor,
total count, and timezone-aware observation time. `clusters` is a complete
database roster of registered execution clusters; `workshops` is a complete
roster of *all retained* workshops; `sessions` and `reservations` are complete
for the requested workshop IDs; `namespaces` is a complete managed-namespace
roster for each registered cluster, not just the requested workshops.

The caller configures one expected database source ID and an exact mapping of
registered cluster IDs to namespace source IDs. These identities must come
from separately reviewed deployment configuration, not from response rows.
The database source must serve all four database rosters at one revision.
Each cluster's namespace pages must stay at one cluster revision. A provider
must honor `expected_revision` by serving that same snapshot or failing;
silently falling forward is prohibited.

The adapter rejects inconsistent source identity, revision, cursor, count,
duplicate row ID, incomplete final page, stale timestamp, unexpected cluster,
or page limit. It then passes rows through the collector's strict projection
and balance checks. Provider exception details are suppressed so endpoint
credentials cannot appear in diagnostics; private row fields are excluded
from the returned inventory.

## Limits of local proof

Tests use deterministic fakes. Neither this adapter nor a provider-supplied
`total_count` proves that a live API returned *all* rows if that API lies,
changes an unpinned snapshot, omits an entire workshop while adjusting its
count, or loses cluster reachability outside the scan. Cross-source atomicity
between database and Kubernetes is not established. Live certification needs
an independently reviewed read-only database and per-cluster implementation,
snapshot/credential provenance, fresh T-30 capture, reconciliation against
live state, and a separate explicit reclaim approval. This contract does not
permit reclaiming retained workshops by itself.
