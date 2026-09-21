# Destination pre-pull attestation (local contract)

The v1 attestation adapter authenticates one claim per planned cluster/image
pair using an HMAC-SHA256 key bound to a named producer and cluster. It checks
the complete eligible-node set against a separate trusted inventory, then
applies the existing pre-pull receipt window and coverage checks. Unknown
producer, missing key/inventory, absent node, duplicate claim, bad MAC, stale
observation, and incomplete per-node proof all fail closed.

The producer key must come from a runtime secret store, never this repository.
The eligible-node snapshot must be collected independently of the producer
claim. Each `evidence_sha256` names an immutable evidence artifact; this local
adapter checks its digest syntax, but does **not** retrieve or hash that
artifact. An authenticated claim proves key possession, not that a node was
actually observed. A deployed producer, artifact verification, independent
inventory freshness, authenticated destination pull, image-signature policy,
and cold/cache-loss recovery still need integration and live certification.

The adapter is deliberately not wired to admission. Its `GREEN-local` status
means the contract tests pass locally, not that event artifact readiness is
live-certified. Existing descriptive v1 receipts remain unchanged.
