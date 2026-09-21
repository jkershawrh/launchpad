# In-flight capacity collector boundary

This iteration defines a local-only, testable collector contract. It does **not**
query any cluster, write live evidence, or change admission. The CLI exits 2
without writing a snapshot. The test fake proves that an explicitly selected
`ClusterTarget`, a complete namespace roster and pod request inventory, node
allocatable, model-slot accounting, and persisted reservation/workshop/seat
identities can produce the existing provider's versioned snapshot.

The observer must use read-only credentials bound to the selected target. It
must enumerate **all** namespaces and pods, not only Launchpad namespaces.
Each pod's effective request includes ordinary containers, init-container
maximums, and pod overhead. Pending pods remain capacity-bearing. Model slots
must come from an explicit, complete source; zero cannot mean “unknown.” The
collector refuses missing, duplicate, stale, or cross-cluster inventory and
never emits `accounting_complete: true` for a partial scan. Snapshot writing
is atomic, private (`0600`), and validated by the production file provider.
An ordinary workshop namespace may carry workshop and seat IDs without an
event reservation ID. Its pods count as external physical usage, not as
consumption of an event reservation. A namespace matching a currently
consumed event workshop must carry the exact reservation/workshop/seat triplet;
partial or mismatched event identity blocks collection without replacing the
previous snapshot.

Future event orders now propagate the reservation ID from the persisted
workshop through each seat request and plan into the namespace labels for both
demo/Showroom and sandbox provisioners. Incomplete event identity fails before
namespace creation. This is local code proof only: existing live namespaces
were not relabeled, and the read-only cluster observer and persisted-workshop
adapter are still required before a live collector can publish evidence. The
CLI intentionally has no fixture mode that could accidentally mint
trusted-looking runtime evidence.

This evidence alone is not an admission lock. The reservation transaction
must recheck fresh evidence and active holds atomically before new orders use
it as an authoritative gate.
