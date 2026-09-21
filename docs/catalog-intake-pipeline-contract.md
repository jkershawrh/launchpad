# Catalog intake pipeline response contract

`contracts/catalog-intake-pipeline-v1.1.yaml` describes the existing read-only
Intake response. It supersedes the narrower v1.0 description; it does not
change the API's `launchpad.redhat.com/catalog-intake-pipeline/v1` wire version.
The original v1.0 file is retained unchanged because its hash is part of the
earlier immutable evidence manifest.

The response may be at `submitted` or `draft-generated`. `approve_source` and
`run_discovery` are display-only eligibility hints, not authorization tokens.
The authenticated mutation endpoints must recheck durable state, source
approval, and worker availability at request time. Certification, review,
promotion, publication, ordering, and live-catalog mutation remain unavailable
through this pipeline. Contract-alignment tests cover both stage values and
the immutable no-promotion boundary.

The admin detail page displays each gate's required evidence and blockers.
Even when discovery has produced a draft with no static findings, artifact and
security review remains blocked with an explicit explanation until separate
certification evidence is collected. Displaying a gate does not run it or
grant publication authority.
