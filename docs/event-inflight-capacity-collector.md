# In-flight capacity collector boundary

This iteration defines a local-only, testable collector contract and a
read-only Kubernetes observer adapter. It does **not** query a live cluster,
write live evidence, or change admission. The CLI exits 2 without writing a
snapshot. Fake-cluster tests prove that an explicitly selected `ClusterTarget`,
a complete namespace roster and pod request inventory, node allocatable,
model-slot accounting, and persisted reservation/workshop/seat identities can
produce the existing provider's versioned snapshot.

The observer must use read-only credentials bound to the selected target. It
must enumerate **all** namespaces and pods, not only Launchpad namespaces.
Each pod's effective request includes ordinary containers, init-container
maximums, and pod overhead. Pending pods remain capacity-bearing. Model slots
must come from an explicit, complete source; zero cannot mean “unknown.” The
collector refuses missing, duplicate, stale, or cross-cluster inventory and
never emits `accounting_complete: true` for a partial scan. Snapshot writing
is atomic, private (`0600`), and validated by the production file provider.
The Kubernetes adapter consumes all paginated list responses, checks a second
namespace roster after the pod scan, excludes terminal pods, and counts only
ready, schedulable, untainted worker allocatable while retaining all active pod
requests as usage. This deliberately understates headroom where a promoted
workload policy may tolerate a dedicated node; per-release placement must be
resolved separately.
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
were not relabeled. The Kubernetes observer exists as local code, but no
approved read-only service-account binding, authoritative model-slot producer,
persisted-workshop adapter, source attestation, or live completeness proof is
connected. A local-only file adapter now checks that a supplied model-slot
observation is complete, target-specific, fresh, and explicitly based on
promoted model concurrency. It does not establish that its policy reference is
authentic or that the slot number is certified; it is not wired to admission.
The CLI intentionally has no fixture mode that could accidentally mint
trusted-looking runtime evidence.

This evidence alone is not an admission lock. The reservation transaction
must recheck fresh evidence and active holds atomically before new orders use
it as an authoritative gate.
