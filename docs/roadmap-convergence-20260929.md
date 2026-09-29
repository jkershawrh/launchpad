# Launchpad roadmap convergence — September 29, 2026

## Decision

The roadmap is now one product backlog with explicit proof accounting. The
Flightpath unchanged-candidate certification remains the staging baseline. New
work does not rewrite that evidence or silently turn partial implementation
into closure.

The staging-to-production sequence is:

1. finish the current unchanged-candidate five-seat Flightpath matrix;
2. fix or classify every RED-live result and rerun only affected five-seat
   catalogs;
3. prove complete reclaim and zero residue;
4. complete rapid cluster onboarding, impact-based recertification, and
   independently promotable Showroom content;
5. rerun the complete unchanged-candidate staging matrix and accept the staging
   gate;
6. advance through security, HA/DR, production-load, operational ownership,
   governance, commercial, and production-home gates;
7. deliver hybrid-cloud federation as a production-scale capability, not as an
   excuse to delay a truthful single-home staging candidate.

## Proof accounting snapshot

- Roadmap tasks: **210**
- Explicit task status records: **210**
- Tasks previously omitted from the status ledger: **124**
- Newly defined tasks: **28** across rapid cluster onboarding, impact-based
  recertification, independent Showroom delivery, and hybrid-cloud federation
- Declared states: **50 GREEN-local**, **5 GREEN-integration**, **155 RED**
- Effective states after the five-method fail-closed rollup:
  **27 GREEN-local**, **2 GREEN-integration**, **181 RED**
- GREEN-live roadmap tasks: **0**

An implementation note or partial proof is not a closed task. A task closes
only when its applicable TDD, EDD, CDD, BDD, and CBT evidence reaches the
declared gate and its security, usability, operability, cleanup, and ownership
requirements are satisfied.

## Staging convergence boundary

### Must close before the staging gate

- Immutable platform candidate and independently identified catalog/runtime/
  content dependencies.
- Every currently viable catalog certified at five seats on Flightpath.
- Functional participant journeys, namespace isolation, model/API behavior,
  and truthful failure classification.
- Full lifecycle proof from order through reclaim.
- Zero namespaces, Routes, RoleBindings, Argo CD Applications, entitlements,
  credentials, and inactive identities after reclaim.
- Cluster-native certification runner with bounded authority and durable,
  hashable evidence.
- Rapid cluster onboarding contract and canary/eligibility workflow.
- Impact graph, risk classification, and targeted five-seat recertification.
- Independent Showroom content identity, preview, bounded promotion, and
  rollback without participant-workload reprovisioning for editorial changes.
- Complete full-catalog regression of the final unchanged staging candidate.

### May remain open at staging but blocks production

- HA PostgreSQL, durable queues/leases, backups, restore, and fencing.
- Three consecutive DR/failback drills and production-home migration proof.
- Production public-edge architecture, identity HA, WAF, and support ownership.
- Full security penetration/isolation suite and accepted threat model.
- Production-shaped load, spike, stress, soak, failure-under-load, upgrade,
  rollback, browser/accessibility, and reconciliation testing.
- Production SLOs, error budgets, paging, incident command, game days, and
  non-author operational continuity.
- Governed AI gateway, model registry, deterministic routing/admission,
  attribution, safety, and provider failover.
- Authoritative resource, inference, cost, outcome, and support telemetry.
- Privacy, retention, deletion, legal, brand, licensing, and responsible-AI
  decisions.
- Rate cards, budgets, showback/chargeback, service tiers, and finance
  reconciliation.
- GTM attribution, customer-success ownership, packaging, and accepted sales
  claims.
- Repository ownership cleanup, modular release boundaries, and any eventual
  OSS distribution gate.

### Production-scale roadmap, not a Flightpath staging blocker

- Hybrid-cloud federation across materially different providers and failure
  domains.
- Pull-based ACM/GitOps fleet registration where justified.
- Residency, sovereignty, locality, disconnected, egress-cost, and
  provider-aware placement.
- Cross-provider degraded-connectivity and dependency-loss certification.
- Provider-aware FinOps and hybrid-cloud capacity forecasting.

## Four newly explicit product tracks

### Rapid cluster onboarding — LP-S036 / LP-T183–LP-T188

One registration contract, least-privilege bootstrap, capability discovery,
fail-closed dependency preflight, canary lifecycle, zero-residue proof, and
audited eligibility. Target: a compatible cluster becomes placement-eligible
in under one operator hour.

### Impact-based recertification — LP-S037 / LP-T189–LP-T195

Independent release identities, dependency graph, risk classification,
evidence reuse rules, concurrent bounded Jobs, targeted five-seat reruns, and
periodic complete regression. Target: ordinary behavioral corrections complete
in 15–30 minutes when capacity is available, without weakening the staging
gate.

### Independent Showroom delivery — LP-S038 / LP-T196–LP-T202

Showroom content becomes an independently signed bundle. Editorial changes use
automated content checks; instructional changes add a bounded journey;
behavioral changes require affected live certification. Atomic refresh and
rollback must not restart participant workloads.

### Hybrid-cloud federation — LP-S039 / LP-T203–LP-T210

Provider-neutral cluster facts, portable dependencies, deterministic
policy/placement, persisted cluster identity, provider failure proof, and
explainable cost/residency decisions. Launchpad stays authoritative; AI may
recommend but never creates eligibility.

## Closure rules

1. Do not mark a task complete from prose that says a component exists.
2. Do not reuse evidence across changed dependency digests or expired cluster
   facts.
3. Do not count a pod-ready result as a usable participant journey.
4. Do not count targeted recertification as the final staging regression.
5. Do not close lifecycle work without zero-residue evidence.
6. Do not close production gates without named human ownership and acceptance.
7. Archive superseded evidence; never delete or rewrite it to make the current
   candidate appear green.

## Immediate execution queue

1. Allow the active Flightpath five-seat matrix to reach a terminal state.
2. Collect every catalog result and the final residue verifier.
3. Build the diagnostic runner already prepared for CPU-RAG and Agent 201
   failure-stage isolation.
4. Run targeted five-seat diagnostics only for RED catalogs.
5. Correct runner defects without changing the platform candidate; if a lab or
   platform defect is proven, create a new candidate rather than mutating the
   current one.
6. Rerun affected five-seat catalogs and prove reclaim.
7. Implement LP-S036, LP-S037, and LP-S038 behind contracts and tests.
8. Run the final complete unchanged-candidate matrix and assemble the staging
   evidence manifest.
9. Request explicit staging acceptance.
10. Begin the production-gate backlog, with hybrid cloud running as a bounded
    parallel production-scale stream.
