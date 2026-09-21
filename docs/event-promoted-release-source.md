# Local promoted-release source boundary

`AuthenticatedPromotedReleaseSource` implements the event artifact requirement
resolver's `get_promoted_release(catalog_id, catalog_release)` interface. It is
local-only and is **not wired into live admission**.

The operator supplies a server-owned signing key (at least 32 bytes), a trusted
registry policy path, and a release-record root. Each release occupies
`<root>/<catalog_id>/<catalog_release>/` with:

- `release.json`: a `launchpad.redhat.com/promoted-catalog-release/v1` record
  containing the exact catalog ID/release, `state: promoted`,
  `runtime_images_complete: true`, all runtime images as immutable `@sha256:`
  references, and one path-plus-SHA-256 release receipt per image.
- `release.sig`: lowercase hex HMAC-SHA-256 over the exact bytes of
  `release.json`, produced by the trusted promoter with the server-owned key.
- Receipt files referenced by the signed record, each satisfying the existing
  artifact release evidence contract and matching its image digest.

The configured root and policy file must be operator-owned and inaccessible to
requesters and workloads. The adapter rejects symlinks at the configured root,
catalog directory, release directory, and within receipt paths; this does not
replace filesystem ownership and permission controls for the root's ancestors.

The adapter verifies the signature, record identity, complete one-to-one
image/receipt coverage, receipt bytes, approved registry origin and component
repository, immutable image references, release checks, registry ownership,
signing identity, and pull grant. A missing release returns `None`; a present
but untrusted or incomplete release raises `PromotedReleaseSourceError`. The
returned `promotion_evidence_id` is the SHA-256 digest of the signed manifest
bytes. Request bodies and runtime health snapshots never define the image set.

The checked-in `config/artifact-registry-policy.yaml` is still **provisional**:
ownership, signing identity, and pull grants are unapproved. It therefore
cannot authorize a release. Before live wiring, an authenticated promotion
producer must publish complete signed manifests, operators must approve the
actual Quay authority and repository grants, and integration must verify
authentic signature/provenance checks, image pullability, and destination
cold-pull evidence. An HMAC receipt is proof of what the trusted promoter
recorded; it does not independently contact Quay or validate an external OCI
signature.
