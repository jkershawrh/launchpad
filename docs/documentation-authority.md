# Documentation authority and drift policy

Launchpad documentation is divided into current product contracts, operational
runbooks, and immutable historical evidence. A dated proof file records what
was true during that run; it is not the current architecture merely because it
remains in Git.

## Canonical current documents

When two documents disagree, use this order of authority:

1. [`ecosystem-architecture-roadmap.md`](ecosystem-architecture-roadmap.md) —
   target product architecture, migration horizons, and decision boundaries.
2. [`architecture.md`](architecture.md) — current pilot topology and the
   concise production-plane contract.
3. [`provisioning-lifecycle.md`](provisioning-lifecycle.md) — order, placement,
   reservation, seat, validation, and reclaim behavior.
4. [`catalog-onboarding.md`](catalog-onboarding.md) — catalog packaging,
   deployment-class selection, artifact promotion, and certification.
5. [`control-plane-dr-roadmap.md`](control-plane-dr-roadmap.md) and
   [`flightpath-dr-runbook.md`](flightpath-dr-runbook.md) — recovery authority.
6. [`observability-architecture.md`](observability-architecture.md) — current
   operational telemetry and production observability target.
7. [`product-delivery-roadmap.md`](product-delivery-roadmap.md) — sequenced
   delivery horizons, epics, stories, tasks, dependencies, and evidence gates.

`README.md` is the entry point and must summarize, not redefine, these
contracts.

The authoritative working defect and feature backlog for the September pilot
is [`pilot-issue-feature-register-20260917.md`](pilot-issue-feature-register-20260917.md).
Operational observations belong there until a durable correction is verified;
temporary event mitigations must not be represented as closed product fixes.

The retained-seat snapshot and the non-destructive plan for observing the
eventual reclaim are recorded in
[`active-seat-inventory-20260917.md`](active-seat-inventory-20260917.md).

The planned StarGate event, logging, evidence, delivery, and product-list
contract is
[`stargate-product-telemetry-contract.md`](stargate-product-telemetry-contract.md).
It defines a target and must not be read as proof that the live integration is
durable or autonomous today.

## Canonical production target

- One dedicated, highly available Launchpad control-plane cluster owns orders,
  lifecycle state, policy, identity integration, placement, evidence, GitOps
  coordination, and audit. It does not run participant workloads.
- A registered fleet of execution clusters provides replaceable capacity.
  Participant seats normally use isolated namespaces on a warm eligible
  cluster.
- A shared AI-serving plane provides private, governed model endpoints and
  feeds readiness, pressure, latency, and availability into placement.
- A stable public edge provides DNS, trusted TLS, identity, entitlement, and
  routing without exposing control-plane or model services directly.
- An approved highly available registry is the artifact source of truth.
  Catalogs deploy signed immutable digests; execution-cluster registries are
  mirrors or caches, never the only copy.

Launchpad does not create a cluster for every seat or every ordinary workshop.
Cluster creation and retirement manage fleet capacity beneath Launchpad. A
catalog selects one of three certified deployment classes:

1. shared-cluster namespace lab (default);
2. dedicated workshop cluster; or
3. dedicated seat cluster (exceptional and explicitly approved).

## Historical evidence

Files with a date in their name, evidence manifests, readiness reports, and
incident findings remain immutable except for an explicit header or index that
clarifies their historical status. Their recorded counts, topology, failures,
and conclusions must not be rewritten to resemble the current system.

Examples include `september-*`, `ha-dr-certification-*`, and retained
capacity-test evidence. Current documents may cite them as RED or GREEN proof.

## Drift-control rules

- Do not describe RHDP, AgnosticV, AgnosticD, Arena, Brutus, Flightpath, or
  Oberon as the permanent production architecture. They are integrations,
  pilot locations, execution targets, recovery candidates, or provenance.
- Do not publish one global seat limit. Publish a certified
  catalog × cluster × exposure-policy limit.
- Do not call `Synced`, `Running`, or a successful image pull functional proof.
  Require the participant journey and zero-residue reclaim.
- Do not use mutable image tags or another execution cluster's internal
  registry as a production catalog dependency.
- Do not let AI override deterministic eligibility, authorization, ownership,
  capacity reservation, or cleanup targeting.
- Update the canonical documents and their contract tests in the same change
  when a product decision changes.
