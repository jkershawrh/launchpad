# Production solution pathways

## Intent

DeepField, StarGate, and GeoLux are candidate production paths in the Intel
internal demo platform. They should appear through Launchpad as coherent,
supportable solutions rather than as loosely connected demo pages.

Launchpad owns ordering, placement, tenant/workshop lifecycle, Showroom,
handoff, capacity, and reclaim. Each solution remains independently deployable
and owns its application release, persistence, security model, APIs, runbooks,
and subject-matter content.

## Product roles

### StarGate: validation and operations path

StarGate continuously scans environments, evaluates readiness rubrics,
classifies failures, forecasts capacity, and proposes or executes policy-gated
remediation. Its primary production role is a shared operations dependency for
Launchpad, not a copy inside each participant namespace.

Launchpad integration should include lifecycle evidence, preflight evaluation,
capacity signals, correlated workshop/session identity, remediation callbacks,
audit records, and explicit fail-open/fail-closed policy by decision type.

A participant journey can demonstrate how a failed lab becomes evidence, a
rubric result, and a governed remediation, using a dedicated synthetic or
seat-scoped environment.

### DeepField: observability and inference-intelligence path

DeepField observes OpenShift fleet signals, reduces noise, correlates events,
routes inference work, and produces findings, forecasts, and advisory actions.
Its primary production role is a shared multi-cluster service with read-only
cluster access and scoped integration events from Launchpad and StarGate.

A participant journey should use synthetic or tenant-scoped telemetry and show
signal ingestion, deterministic compression, inference routing, correlation,
fleet health, and an advisory outcome. It must not grant participants access to
unrelated cluster or tenant telemetry.

### GeoLux: governed agentic-inference path

GeoLux provides hypothesis generation/validation, constraint classification,
model-predictive control, geometric stability analysis, DeepField routing, and
scenario replay. It is a production solution above the foundational StarGate
and DeepField contracts, not a prerequisite for basic Launchpad provisioning.

A participant journey should enroll or select a scoped agent, run a hypothesis
and constraint workflow, observe stability/drift, route approved inference, and
replay the decision with an auditable outcome. Any action execution must remain
policy-gated and separate from advisory analysis.

## Deployment shapes

Use two explicit shapes instead of one oversized lab:

1. **Shared production service** — long-lived StarGate, DeepField, or GeoLux
   deployment with managed persistence, authentication, monitoring, backup,
   upgrades, and service ownership.
2. **Launchpad experience** — a lightweight seat namespace containing Showroom,
   terminal, scoped credentials, synthetic/sample data where necessary, and
   links to the permitted shared-service views or APIs.

Deploying a dedicated solution instance per workshop is an allowed exception
when data isolation, destructive exercises, or version certification requires
it. The catalog item must declare that resource profile explicitly.

## Common graduation gates

Each solution advances through the same gates:

1. **Product contract** — named owner, supported use case, repository/ref,
   architecture, dependency inventory, API/event schemas, and version policy.
2. **Security and tenancy** — OAuth/service identity, least privilege, secrets,
   TLS, data boundaries, auditability, and safe remediation policy.
3. **Deployment** — GitOps/Helm packaging, migrations, health/readiness probes,
   durable images, backup/restore, upgrade and rollback procedures.
4. **Launchpad catalog** — capabilities, cluster eligibility, models, resource
   profile, persistence, TTL, capacity formula, handoff, and cleanup contract.
5. **Showroom journey** — repository-owned Antora content, a measurable outcome,
   correct cluster/tenant personalization, and no inaccessible placeholder links.
6. **Automated validation** — API health, application behavior, model calls,
   event contracts, isolation, failure cases, and deterministic cleanup.
7. **Visual certification** — real-browser completion at representative seats,
   including dashboards, terminal actions, errors, navigation, and accessibility.
8. **Scale and operations** — cohort test, soak, alerts, SLOs, support ownership,
   incident response, showback, and zero-residue bulk reclaim.

## Recommended delivery sequence

### Slice 1: StarGate operational integration

- Validate existing Launchpad/StarGate contracts against live deployments.
- Publish lifecycle evidence and workshop correlation IDs.
- Consume health/capacity results without allowing automatic remediation first.
- Add the admin view and a synthetic failure-to-rubric Showroom journey.
- Graduate remediation from recommend-only to narrowly approved low-risk actions.

### Slice 2: DeepField observability journey

- Register Oberon and Arena as read-only monitored targets.
- Validate signal/event contracts from Launchpad and StarGate.
- Expose tenant-safe or synthetic datasets for the participant experience.
- Add the signal-to-finding-to-advisory Showroom journey.
- Prove inference routing, degradation behavior, and resource cost under a cohort.

### Slice 3: GeoLux governed inference journey

- Freeze the StarGate and DeepField interfaces GeoLux depends on.
- Deploy GeoLux with its own PostgreSQL lifecycle, OAuth, and approved MaaS routes.
- Add a hypothesis-to-constraint-to-stability-to-replay Showroom journey.
- Keep actions advisory until policy, audit, rollback, and human approval pass.
- Certify concurrent users and repeatable scenario reset before catalog promotion.

## Promotion states

Use a visible state for every solution path:

- **Discovery:** architecture and dependencies are still being resolved.
- **Incubating:** deployable by maintainers; contracts and content are changing.
- **Pilot:** ordered through Launchpad for controlled internal cohorts.
- **Production candidate:** all gates pass except repeated scale/operations evidence.
- **Production:** published support envelope, owners, SLOs, runbooks, and rollback.

Initial roadmap placement:

- StarGate: **Incubating integration**
- DeepField: **Incubating integration**
- GeoLux: **Discovery**, pending dependency and contract review

These states describe Launchpad portfolio readiness, not the maturity claims of
the individual repositories.
