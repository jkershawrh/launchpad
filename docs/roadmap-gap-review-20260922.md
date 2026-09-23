# Launchpad roadmap gap review — 2026-09-22

## Decision summary

The product roadmap is broad enough to describe the intended product, but the
proof ledger is incomplete. The Markdown roadmap contains 182 tasks across 29
epics and 35 stories. After this review, 55 tasks have explicit status records:
47 GREEN-local, five GREEN-integration, and three RED. The remaining 127 tasks
have no explicit status entry and must be treated as RED/untracked.

Six task records can be updated from evidence already present:

- `LP-T014`: GREEN-local for authenticated, source-bound catalog render claims.
- `LP-T060`: RED; VEF can receive usage aggregates but authoritative metering is absent.
- `LP-T061`: RED; cost-allocation semantics exist but approved rate cards and finance reconciliation do not.
- `LP-T074`: GREEN-local for atomic local persistence, replay, and tamper detection; the production outbox remains open.
- `LP-T133`: GREEN-local for versioned VEF telemetry fields, completeness rules, and local integrity.
- `LP-T139`: GREEN-local for VEF sensitive-field rejection; platform-wide privacy enforcement remains open.

No task can honestly advance to GREEN-live from this evidence. The release
rubric remains 0/100 because live, production-shaped, repeatable proof is still
absent from every critical release category.

## Structural gaps

### VEF is not an explicit delivery stream

The current delivery model combines SRE, operational observability, evidence,
support, and FinOps in `observability-finops`. That obscures the boundary agreed
for VEF. The next contract revision should separate:

- operational observability and SRE: health, incidents, SLOs, alerts, traces,
  support, and operational dashboards;
- VEF analytics and cost: sanitized outcomes, unit economics, allocation,
  chargeback readiness, value evidence, and finance reconciliation;
- GTM attribution: accepted opportunity and sales influence, which remains
  outside both VEF and SRE.

### Status accounting is fail-open by omission

Only 30 percent of roadmap tasks have status entries. The dashboard correctly
renders tracked evidence, but omission is too easy to misread as future work
rather than RED. Every roadmap task needs an explicit record containing owner,
state, methods, dependencies, next evidence, target gate, and last review time.

### Evidence authenticity is uneven

Several components validate internally consistent receipt fields without yet
authenticating the runtime, signer, source inventory, observation time, or
collection path. Intake render authentication now has a local contract, but no
real trusted renderer identity/key or authentic receipt has been provisioned.
The same declared-versus-authentic distinction must be audited across capacity,
artifact, lifecycle, cleanup, cost, and model evidence.

### Data-product operations are incomplete

VEF now has versioned aggregates and a local durable ledger, but it lacks:

- PostgreSQL HA and transactional outbox integration;
- producer authentication, fencing, replay cursors, retries, and dead letters;
- schema compatibility policy and a governed schema registry;
- freshness and completeness SLOs;
- backfill, recomputation, and correction versioning;
- backup, restore, retention, legal hold, and deletion workflows;
- key rotation and recovery after signing-key compromise.

### Measurement sources are missing

The receiving schema must not be mistaken for measurement. Authoritative
adapters are still needed for consumed CPU, memory, storage, network, image
distribution, public edge, model requests/tokens/latency/retries, human support,
participant outcomes, and reclaim residue. Direct model endpoints prevent
reliable per-seat attribution until the governed gateway becomes the supported
path or another authenticated correlation mechanism is approved.

### Financial governance is missing

VEF can distinguish allocated and unallocated cost, but Launchpad has no
approved rate-card authority, effective-date/version rules, cost-center mapping,
budget/quota policy, invoice reconciliation, shared-cost allocation approval,
or dispute/correction workflow. Small-cohort suppression is also needed before
showback can expose business slices without reidentification risk.

### Immutable evidence conflicts with deletion requirements

The roadmap separately calls for append-only evidence and privacy deletion.
It does not yet define how cryptographic receipts remain verifiable after
participant-linked source records are deleted. The production design needs
purpose separation, pseudonymization, tombstones, retention classes, and a
documented deletion-versus-legal-hold decision.

### Release identities need two dimensions

Platform releases and lab/content releases can evolve independently. The
convergence matrix should bind both identities so a certified platform does not
silently inherit uncertified Showroom, model, prompt, dataset, or wardrobe
content, and a certified lab does not silently inherit a changed platform.

### External dependency objectives are not consolidated

Cloudflare/public edge, enterprise DNS and certificates, identity providers,
registries, Git providers, storage, and model endpoints all affect the
participant journey. Their ownership, support hours, error budgets, fallback
behavior, and evidence requirements need one dependency/SLA register.

### Human ownership is temporarily resolved, not operationally resilient

Jonathan Kershaw is the interim decision owner. Production still requires
secondary owners, access custody, escalation paths, change authority, incident
roles, and an independent non-author proving deployment, diagnosis, upgrade,
restore, and reclaim.

## Recommended convergence order

1. Add explicit RED records for all 127 untracked tasks.
2. Version the delivery model to separate VEF analytics/cost from SRE operations.
3. Provision and authenticate the trusted intake renderer; keep promotion blocked until live certification.
4. Implement the PostgreSQL/outbox form of the VEF ledger with fencing, replay, dead letters, retention, and restore proof.
5. Add authoritative lifecycle, resource, inference, participant-outcome, and support adapters.
6. Approve privacy, retention, rate-card, cost-center, allocation, and finance-reconciliation contracts.
7. Bind platform and content release identities in the convergence matrix.
8. Run unchanged-candidate integration, canary, staging, rollback, security, and production-shaped certifications.

## Boundaries of this review

This review changed only roadmap/status documentation and the generated roadmap
dashboard. It did not deploy code, change cluster context, provision or reclaim
labs, alter public access, rotate credentials, or claim live certification.
