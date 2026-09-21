# Pre-pull artifact and node-inventory evidence (local contract)

`verify_prepull_evidence` extends the existing HMAC attestation **without
changing its API or admission behavior**. It requires one exact, complete node
inventory per planned cluster from a separately authenticated source and an
injected read-only content store for each per-node `evidence_sha256`. It
rehashes at most 64 KiB of proof bytes per node and verifies the proof's exact
plan, cluster, image, producer, node, timestamp, mirror, and success fields.
Missing bytes, digest mismatch, duplicate JSON keys, stale/future inventory,
untrusted source, extra or missing nodes, and oversized inputs fail closed.

The inventory source ID is pinned by trusted cluster configuration and cannot
be the pre-pull producer ID. Its observation must fall within the immutable
plan window and be no older than five minutes at verification. A `complete`
marker and nonempty resource version are required. Those fields are only
trustworthy when the caller obtains the snapshot from an independently
authenticated, complete scheduler-aware inventory adapter; caller-supplied
labels alone do not establish provenance. Likewise, proof bytes can still be
false assertions from a compromised or incorrectly implemented producer.

This module makes no Kubernetes or registry calls and cannot certify a real
destination pull or current node cache. It is not connected to order admission.
`GREEN-local` means only that the injected inputs passed the offline checks.
Deployment of the producer and inventory adapter, signed-image enforcement,
authenticated pulls, cold-node and cache-loss tests, and live per-cluster
rehearsals are still required before any admission gate is enabled. The
[contract](../contracts/event-artifact-prepull-evidence-v1.yaml) defines the
bounded input and output shapes.
