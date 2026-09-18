# Parallel agentic delivery and convergence

## Purpose

Launchpad is delivered through bounded vertical streams that can discover,
implement, test, and assemble evidence in parallel. Parallelism ends at a
single convergence path. A feature stream cannot activate a catalog, mutate a
live environment, rotate a shared credential, reclaim a retained session, or
promote itself.

This model covers the whole product path from pilot through staging and
production. Usability is a release invariant throughout that path, not a late
UI phase and not solely the participant-experience stream's responsibility.
Every stream must preserve the current usable path and prove its effect on the
participant, instructor, requester, administrator, and operator journeys at
each promotion gate.

The machine-readable authority for stream ownership, dependencies, shared
contracts, work-in-progress limits, and pivots is
[`delivery-streams-v1.yaml`](../contracts/delivery-streams-v1.yaml). The
machine-readable integration authority is
[`convergence-matrix-v1.yaml`](../certification/convergence-matrix-v1.yaml).

## Operating model

At most four implementation streams are active initially. A stream owns a
vertical outcome, not merely a UI or backend component. It works against a
frozen contract version for one convergence candidate and produces local
TDD/EDD/CDD/BDD/CBT evidence without touching live participant resources.

Parallel work may improve production readiness without interrupting usable
pilot capabilities. A regression in discovery, ordering, access, instructions,
workspace execution, observability, support, resume, or reclaim blocks
convergence even when its component-level tests are green.

The convergence stream alone may assemble shared changes and request an
explicitly approved live operation. Its sequence is:

1. accept stream evidence and freeze candidate contracts;
2. run producer/consumer compatibility and integrated journeys;
3. create one real canary seat per affected catalog;
4. run the required 1-, 5-, and 25/30-seat certification stages;
5. prove security, capacity, failure recovery, rollback, and cleanup;
6. promote the unchanged signed artifacts; and
7. preserve evidence and the tested rollback identity.

There is one candidate in convergence at a time. A future candidate may begin
stream-local work against a new contract version, but it cannot alter the
candidate already being certified.

## Streams

The delivery model defines thirteen streams:

1. automated lab intake and certification;
2. artifact supply chain and authoritative registry;
3. repeatable event orchestration;
4. capacity engineering, forecasting, and admission;
5. participant, instructor, requester, and admin experience;
6. security, identity, isolation, and governance;
7. high availability, disaster recovery, and fleet lifecycle;
8. control-plane portability and earned promotion;
9. SRE, observability, evidence, support, and FinOps;
10. DeepField, StarGate, and GeoLux or GCL integrations;
11. lab content, Showroom, and AI workload performance; and
12. product, go-to-market, sales enablement, and customer success; and
13. convergence, certification, and staged promotion.

The initial four active implementation streams are intake, artifact supply,
event orchestration, and capacity admission. Security and portability contract
work follows as a stream slot becomes available; this prevents the human
product and architecture owner from becoming an unbounded review queue.

## Shared-contract rule

Each shared contract has one owner, declared consumers, a stable version, and a
repository path. A consumer may not silently reinterpret the contract. A
breaking change creates a new version and a compatibility window. The prior
version remains supported until convergence proves every registered consumer
has moved or the release explicitly removes it.

Contract change is not synonymous with live change. Stream-local and contract
tests can proceed using fixtures, rendered manifests, test containers, and
isolated control planes. Live cluster changes remain prohibited outside the
approval-gated convergence stream.

## Pivot policy

Pivots are expected and preserve history:

- **Stream-local:** replan one stream without invalidating unrelated evidence.
- **Contract:** version the affected producer/consumer interface and run delta
  compatibility proof.
- **Product/capacity:** rebaseline demand, capacity, sequencing, and release
  evidence. The pilot change from 90 to 270 seat-environments is the reference
  case.
- **Emergency/live:** freeze promotion, protect active work, restore known-good
  behavior, then create a failing regression test before productizing the fix.

Every pivot records its trigger, decision owner, affected streams and
contracts, capacity and security impact, evidence retained or invalidated,
delta-proof plan, rollback or abandonment path, and new convergence target.
Past evidence is never rewritten to make a pivot look as though it did not
happen.

## Earned promotion

Environment names do not confer maturity. The same immutable release earns:

`GREEN-local → GREEN-integration → GREEN-canary → GREEN-staging →`
`GREEN-production-limited → GREEN-production`

The convergence matrix defines the evidence required at each gate. Promotion
requires the unchanged image digests, catalog releases, schemas, policies, and
rollback identity tested at the prior gate, plus a usable end-to-end journey
at that gate's declared scale. Production additionally requires three
consecutive certifications, migration and failback proof, zero critical or
high security findings, and accountable user and human-owner acceptance.

Production readiness is broader than a successful maximum-seat test. The
candidate must pass baseline, load, spike, stress, endurance, and soak profiles;
failure and recovery while under load; active-session upgrade, schema migration,
rollback, and API compatibility; supported browser and accessibility journeys;
and post-recovery data and cleanup reconciliation. Thresholds come from a
versioned service profile rather than an informal test expectation.

The SRE operating contract adds SLIs, SLOs, error budgets, participant-facing
synthetics, paging, escalation, incident communications, post-incident review,
telemetry quality and cost controls, and named service/support ownership. Pod
readiness alone is never a production availability signal.

The product release also has business gates. Privacy-safe field activity may be
linked to a commercial opportunity only with a declared purpose, consent, and
opportunity-owner acceptance. Activity, completion, influence, and revenue are
separate states. The GTM stream packages validated solution plays, enablement,
service tiers, customer-success follow-up, and the feedback loop into product
and architecture decisions without inferring unsupported revenue.

Data and AI governance cover collection purpose, consent, retention, deletion,
pseudonymization, geographic/export review, model and prompt quality, drift,
prompt injection, tool abuse, provider terms, dataset rights, OSS licensing,
SBOM/provenance, trademarks, and acceptable use. Unknown purpose blocks data
collection; an unapproved model, dataset, or material safety finding blocks
promotion.

## Control-plane portability

Portability begins before a permanent home is selected. The target must be
reconstructable from declarative source plus approved secrets and durable
state. Certification covers clean install, database and identity restore,
registry and object-store reachability, execution-cluster reconnection,
in-flight reconciliation, edge cutover, rollback, and zero-residue reclaim.

Arena, Brutus, Oberon, and Flightpath are never implicit sources of truth.
Execution-cluster registries are caches or synchronized mirrors; the database,
identity, registry, catalog, policy, and evidence authorities are independently
recoverable.

## Validation

Run the governance gate locally with:

```bash
make delivery-governance
```

CI rejects unknown or cyclic dependencies, duplicate ownership, illegal live
mutation authority, missing contract paths, incomplete proof methods,
unsupported green claims, missing evidence, and out-of-order promotion gates.
