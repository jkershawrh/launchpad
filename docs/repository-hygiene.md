# Repository retention and pruning policy

Repository cleanup is deliberately post-event work. Do not remove, relocate,
or rewrite live-pilot source while active workshops depend on the current
commit, images, content, or operational scripts. Documentation authority and
historical-evidence handling are defined in
[`documentation-authority.md`](documentation-authority.md).

Launchpad contains current runtime source, catalog and Showroom packages,
certification evidence, and historical integration experiments. Similar names
do not mean that files are interchangeable or safe to remove.

The current sanitation effort is governed by
[`../contracts/repository-sanitization-v1.yaml`](../contracts/repository-sanitization-v1.yaml).
It is **not** an OSS extraction. It preserves the Red Hat and Intel joint
product identity, Red Hat platform technology, current catalog and Showroom
content, and the Flightpath control/execution path while removing obsolete RHDP
and AgnosticV coupling and sanitizing historical operational material.

## Protected pilot scope

Until the September pilot is complete, do not prune:

- `backend/`, `frontend/`, or `admin/`;
- the `intel-llm-cpu-serving`, `intel-xeon6-agent-201`, or
  `multi-agent-quickstart` catalog, content, site, deployment, contract, or test
  paths;
- Arena, Brutus, Flightpath, public-access, model, lifecycle, or tunnel
  deployment source;
- recovery tags or evidence referenced by the current readiness gate; or
- untracked operator runbooks, DNS manifests, tunnel scripts, and day-of
  artifacts until their ownership and destination are resolved.

## Retention classes

### Source of truth

Application source, deployment definitions, schemas, contracts, catalog
packages, tests, and current runbooks remain in Git and must be reviewable.

### Immutable evidence

Evidence referenced by a checksum, release decision, or another immutable
evidence record remains intact until a replacement index preserves that chain.
The public-access validation matrix revisions are therefore retained even when
superseded.

Long term, Git should keep a signed current summary and evidence manifest per
release or event. Raw seat-level output should be published as a durable CI,
release, or object-storage artifact pinned by digest.

### Generated output

Test receipts, rendered sites, build output, dependency trees, local
kubeconfigs, and temporary tunnel files are not source. They must remain
ignored and should be uploaded as workflow artifacts when a run needs them.

### Historical design

RHDP/AgnosticV, infra01, older Oberon, and superseded catalog material may be
valuable design history. Archive or remove it only after current consumers,
tests, image builds, and historical session rendering no longer depend on it.

## Safe prune sequence

1. Create a recovery tag and capture an exact tracked-file manifest.
2. Identify every code, documentation, CI, catalog, database, and evidence
   reference to the candidate paths.
3. Introduce catalog tombstones or migrations before removing catalog metadata.
4. Render Antora, Kustomize, and Helm inputs and build affected container
   images.
5. Run backend, requester, admin, contract, and secret-scanning checks.
6. For runtime changes, prove create, validate, participant use, and
   zero-residue reclaim for all three pilot labs.
7. Submit one reversible PR per cleanup class. Do not rewrite history or force
   push to hide old artifacts.

## Current cleanup phases

- **Phase 1 — source-of-truth cleanup:** remove tracked generated receipts,
  correct README/TODO guidance, and replace the obsolete infra01 deployment
  workflow with a manifest-only deployment gate.
- **Phase 2 — evidence redesign:** move acceptance behavior into code,
  contract, integration, and certification tests before reducing historical
  evidence coupling.
- **Phase 3 — catalog retirement:** audit active and historical sessions,
  introduce tombstones, and then retire superseded catalog/content packages.
- **Phase 4 — legacy extraction:** extract still-used sandbox/demo components,
  remove fallback provisioning paths, update CI, and archive unused RHDP assets.
- **Phase 5 — repository boundaries:** move large content media,
  presentations, and raw certification output to versioned durable storage or
  focused repositories.

Before Phase 1 begins, publish an ownership inventory for every top-level path,
classify it as runtime source, catalog/content source, environment/GitOps,
immutable evidence, generated output, local operator material, or historical
provenance, and record its consumers. The target split is product, catalog and
content, and sanitized environment configuration; extraction follows stable
contracts and independent releases rather than preceding them.
