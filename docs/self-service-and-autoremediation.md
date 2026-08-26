# Self-service and auto-remediation operating model

## Target state

Launchpad should serve routine demand and recover from known, low-risk failures
without requiring an operator to shepherd every request. Humans remain
responsible for policy, catalog approval, security boundaries, capacity
expansion, shared services, and novel or high-impact failures.

The target loop is:

```text
declare intent -> admit and place -> provision -> validate -> hand off
       ^                                                   |
       |                                                   v
learn from evidence <- audit <- remediate or escalate <- observe
```

Self-service and auto-remediation use the same contracts: desired state is
versioned, placement is persisted, every mutation is scoped and auditable,
validation decides whether the outcome is acceptable, and cleanup is part of
the product rather than an afterthought.

## Self-service surfaces

### Environment consumers

Participants and instructors can discover approved catalog items, preview
capacity, order individual environments or workshops, follow readiness, obtain
personalized handoff links, retry permitted failures, and reclaim what they
own. The portal must explain why a request is blocked and what the user can do
next.

### Content integrators

The CI self-service path should eventually provide a guided contribution flow:

1. Choose a quick-start, guided-build, or open-sandbox template.
2. Declare audience, capabilities, models, resource profile, TTL, Showroom
   source, validation, and cleanup contract.
3. Generate repository-native catalog/content/test scaffolding.
4. Run schema, policy, security, rendering, and one-seat preview checks.
5. Produce a reviewable pull request and evidence bundle.
6. Promote through one-seat, five-seat, and supported-scale certification.

This flow automates mechanics, not approval. Git remains the source of truth and
production catalog promotion remains reviewed.

### Tenant owners

Tenant owners should manage approved membership, defaults, quotas within an
assigned envelope, branding, active orders, scheduled events, and showback.
They must not gain cluster-level access through the tenant interface.

### Platform operators

Operators use one fleet view for eligibility, capacity, reservations, lifecycle
failures, model availability, Showroom health, cleanup, and remediation history.
Manual action should be reserved for exceptions the policy engine cannot safely
resolve.

## Remediation maturity levels

| Level | Behavior | Release requirement |
|---|---|---|
| 0 — Observe | Detect and attach evidence; operator acts manually | Reliable identity correlation and alerts |
| 1 — Recommend | Classify failure and propose a bounded action | Tested runbook, confidence, affected-resource preview |
| 2 — Approve | Operator approves an otherwise automated action | Authentication, authorization, audit, idempotency |
| 3 — Auto-remediate | Execute allow-listed low-risk actions automatically | Circuit breakers, retry budget, post-action validation, rollback/escalation |
| 4 — Optimize | Tune placement, warm pools, and capacity from measured outcomes | Stable SLOs, drift controls, explainable policy changes |

Do not jump directly from detection to autonomous mutation. Each failure class
must graduate independently through these levels.

## Initial auto-remediation allow-list

Good first candidates are deterministic, session-scoped, retry-safe, and easy
to verify:

- retry validation after a bounded readiness delay;
- resync a session's existing Showroom Argo CD Application;
- recreate a missing generated Route or other owned namespaced resource from
  the persisted provisioning plan;
- restart an unhealthy Launchpad-managed namespaced workload within a retry
  budget;
- retry failed-seat provisioning without moving the workshop to another
  cluster;
- retry cleanup on the persisted target cluster;
- reconcile stale session records when labeled resources are already gone;
- reclaim expired sessions and release their capacity reservations;
- warm an approved model endpoint when policy allows and readiness confirms the
  route before new placement.

## Actions that always require human approval

- changing RBAC, Secret material, trust bundles, or identity configuration;
- installing, upgrading, or removing cluster-scoped Operators or CRDs;
- changing cluster capacity, storage, ingress, DNS, or certificates;
- moving an active session or splitting a workshop across clusters;
- deploying, deleting, or changing access to shared model-serving workloads;
- deleting unlabeled, ambiguously owned, or cross-tenant resources;
- raising tenant limits or bypassing admission and capacity policy;
- modifying remediation policy, confidence thresholds, or retry budgets.

## Remediation execution contract

Every attempted action must record:

- failure class and supporting evidence;
- session, workshop, seat, tenant, catalog version, and `cluster_ref`;
- policy version, risk level, confidence, and approval identity when required;
- exact target resources and preconditions;
- idempotency key and retry count;
- action start/end timestamps and result;
- post-action functional validation;
- rollback result or escalation reason.

The executor must fail closed when ownership, credentials, target cluster, or
policy is ambiguous. It must never retry against a different cluster. A circuit
breaker stops a failure class when its success rate degrades or its retry budget
is exhausted.

## Control-plane resilience

For the platform to serve itself, its own critical services need the same
discipline as participant environments:

- readiness and liveness checks that reflect database, queue, Argo CD, cluster,
  and model dependencies;
- durable queued work so API restarts do not lose provisioning or cleanup;
- leader election or single-writer guarantees for reconcilers;
- persisted capacity reservations and lifecycle transitions;
- backup and restore tests for PostgreSQL and required Secret references;
- deployment health gates and automated rollback for the portal/backend;
- SLOs for request acceptance, provisioning, validation, reclaim, and
  remediation;
- alerts when the automation itself is unhealthy or suppressed.

Auto-remediation must not depend solely on the component it is repairing. For
example, external OpenShift/Argo health and a durable controller should recover
a failed backend deployment; an in-process timer alone cannot.

## Graduation plan

1. Normalize failure classes and evidence across provisioning, validation,
   Showroom, model access, and cleanup.
2. Publish operator runbooks and measure manual outcomes.
3. Implement recommend-only actions and compare recommendations with operator
   decisions.
4. Add approval-gated execution for session-scoped actions.
5. Auto-enable one low-risk failure class at a time with a small retry budget.
6. Prove successful post-action validation and zero cross-session impact under
   fault injection and concurrent workshops.
7. Add circuit breakers, outcome dashboards, and automatic downgrade to
   recommend-only mode.
8. Extend automation to predictive placement and model warm policy only after
   stable operational evidence exists.

StarGate is the intended validation and failure-classification plane; DeepField
can contribute fleet and inference signals. Launchpad remains the authority for
session/workshop lifecycle mutations and must enforce the remediation policy at
the execution boundary.
