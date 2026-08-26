# Persona onboarding guide

This guide is the starting point for people joining the internal Intel x Red Hat
AI Launchpad. It explains what each persona can do, what access they need, and
which workflow they should follow.

Launchpad is self-service for ordering and using approved environments. Changes
to catalog definitions, Showroom content, placement policy, shared operators,
model serving, or the platform itself remain Git-reviewed and are promoted by
the platform team.

## Persona map

| Persona | Primary goal | Normal interface | Required access |
|---|---|---|---|
| Participant | Complete an individual lab or assigned workshop seat | Showroom, workspace, scoped OpenShift Console | Workshop link or Launchpad login |
| Instructor / workshop owner | Order, monitor, hand off, and reclaim a multi-seat workshop | Partner portal workshop view | Launchpad login and assigned tenant |
| Content integrator (CI) | Add or revise a catalog experience and its guided content | Git repository, local tests, preview deployment | Repository contribution access; no cluster-admin required |
| Tenant owner / partner lead | Manage who orders against a tenant and review usage | Partner portal and showback views | Tenant assignment; administrative help for membership changes |
| Platform operator | Operate capacity, lifecycle, failures, models, and clusters | Admin dashboard, OpenShift, Argo CD | Launchpad admin role and least-privilege cluster access |
| Platform developer | Change APIs, portal behavior, adapters, or deployment automation | Repository, test suites, development environment | Repository write access; deployment access only when assigned |

## Shared concepts

- An **individual lab** is one order for one environment.
- A **workshop** is one order containing up to 25 isolated participant seats.
- A **seat** is one participant namespace and its personalized access links. A
  25-seat workshop is one workshop, not 25 unrelated workshop orders.
- A **quick start** demonstrates a focused capability.
- A **guided build** combines a provisioned workspace with step-by-step Showroom
  content.
- An **open sandbox** provides a namespace-scoped OpenShift development
  environment. It does not provide cluster-admin access.
- Selected AI models remain centrally hosted behind LiteLLM. A sandbox receives
  scoped API access to selected models; model weights are not loaded into the
  sandbox pod.
- Operators are installed and maintained at cluster scope by platform
  operators. Labs discover and use approved operators rather than installing a
  separate Operator for every seat.

## Participant onboarding

### Before the lab

1. Obtain the participant link from the instructor or open the assigned session
   in **My Labs**.
2. Confirm that the session or seat says `ready` before beginning.
3. Use the **Visual Guide** for instructions and the **Live Workspace** or
   OpenShift Console for exercises.
4. Use only the namespace assigned on the session page.

### Access expectations

- OpenShift sandboxes receive namespace-level `edit`, not cluster-admin.
- Workshop URLs and credentials are seat-specific and must not be shared across
  participants.
- API keys shown in a handoff package are temporary and scoped to the lab.
- Reclaiming the session removes its generated namespace and access.

If a page is unavailable, record the session ID, seat number, URL, approximate
time, and visible error before contacting the instructor.

## Instructor and workshop-owner onboarding

### Order flow

1. Open **Request Environment → Multi-seat Workshop**.
2. Choose the tenant, guided catalog item, seat count, and TTL.
3. Run the capacity preview. The preview must identify an eligible cluster for
   the entire workshop.
4. Confirm the order once. Launchpad keeps all seats on the selected cluster and
   will reject the order before provisioning if the complete workshop does not
   fit.
5. Wait for the workshop to reach `ready`; do not distribute URLs while seats
   are still provisioning or validating.
6. Export or distribute the per-seat handoff links.

### Event-day checks

- Open representative seats before the event and verify Showroom navigation,
  workspace access, OpenShift Console access, and the documented exercise.
- Monitor failed seats and use **Retry failed seats** only after reviewing the
  error.
- Reclaim the workshop after the event and confirm cleanup completes.
- Treat the published 25-seat limit as the supported envelope. Larger events
  require a separate capacity certification and platform-team approval.

Use [oberon-workshop-readiness.md](oberon-workshop-readiness.md) for the current
certification evidence and visual release gate.

## Content integrator (CI) onboarding

A CI owns the reproducible participant experience. That includes the catalog
contract, provisioned workload, Showroom journey, validation evidence, handoff,
and cleanup behavior. A CI does not need to fork AgnosticV/AgnosticD for the
internal Intel platform and should not make live cluster changes as the source
of truth.

### Access and local setup

Request:

- read/write or pull-request access to this repository;
- a reviewer from the Launchpad platform team;
- access to a non-production tenant for end-to-end certification;
- an Oberon account only when live certification is scheduled.

Do not commit kubeconfigs, tokens, passwords, MaaS keys, participant exports, or
Secret values. Use Secret references in configuration and the approved secret
delivery process.

Run the existing verification suites before starting:

```bash
.venv/bin/pytest -q backend/tests

cd frontend
npm test -- --run
npm run build
```

### Files owned by a catalog experience

Create or update only the pieces the experience needs:

```text
catalog/<catalog-id>/catalog-item.yaml     Catalog contract and requirements
content*/modules/ROOT/pages/*.adoc         Participant Showroom pages
content*/modules/ROOT/nav.adoc             Guided navigation
backend/tests/                              Provisioning and API contracts
frontend/src/                               Portal behavior, when new inputs are required
deploy/                                     Reproducible manifests or overlays
```

Use `content-operators/` for the operator workshop and `content/` for the shared
Launchpad guide. Keep all Showroom/Antora source in this repository.

### CI delivery contract

Every new or materially changed experience must define:

1. **Audience and outcome** — who uses it and what success looks like.
2. **Catalog metadata** — stable ID, category, version, defaults, required
   capabilities, required models, and provisioner/validation references.
3. **Inputs** — every user choice exposed in the portal, with safe defaults.
4. **Provisioning** — idempotent, labeled resources scoped to the persisted
   session, tenant, workshop, seat, and cluster.
5. **Showroom** — welcome, access, exercise, verification, and completion pages;
   no stale product or cluster wording.
6. **Validation** — pod/workload readiness plus functional URL, Console, and
   model-call checks where applicable.
7. **Handoff** — correct personalized URLs and temporary credentials.
8. **Cleanup** — retry-safe reclaim with zero remaining namespace, Route, and
   Argo CD Application residue.
9. **Showback** — useful duration and resource attribution.
10. **Evidence** — automated tests and a recorded end-to-end certification.

### Required test progression

Follow red/green/refactor and retain regression coverage:

1. Schema and catalog unit tests.
2. API and UI contract tests.
3. Provisioning-plan and generated-manifest tests.
4. One-seat integration test.
5. Visual Showroom walkthrough in a real browser.
6. Reclaim and orphan check.
7. Five-seat workshop test for guided content.
8. Twenty-five-seat certification only when the experience is intended for the
   supported workshop envelope.

Use a test matrix covering happy path, missing capability, unavailable model,
capacity rejection, interrupted provisioning, validation failure, retry, and
cleanup. A catalog item is not ready merely because its pods are running.

### Pull-request handoff

Include the catalog/version changed, personas affected, test commands and
results, screenshots of participant-facing changes, one successful session ID,
reclaim evidence, rollback notes, and any new operational dependency. Platform
operators perform the production promotion.

## Tenant-owner onboarding

- Confirm the correct tenant and branding before ordering.
- Request membership changes from a Launchpad administrator; do not share a
  common user credential.
- Review active sessions and workshops before retrying a rejected order.
- Reclaim unused environments so tenant limits and fleet capacity remain
  available.
- Use showback for attribution; it is not yet a billing statement.

See [tenancy.md](tenancy.md) for isolation and limit behavior and
[showback.md](showback.md) for usage records.

## Platform-operator onboarding

Operators own the control plane, shared services, and production promotion:

- Launchpad API, portal, admin UI, PostgreSQL, Argo CD, and central LiteLLM run
  on Oberon.
- Oberon and Arena are execution targets. A session's persisted `cluster_ref`
  determines provisioning, validation, reconciliation, URL generation, and
  cleanup.
- Never change the current kubeconfig context during Launchpad operations. Use
  an explicit context or kubeconfig for every command.
- Never use or retain kubeadmin credentials for remote automation. Use the
  least-privilege Launchpad service account and Secret reference.
- Do not retry cleanup against another cluster or migrate a live session.
- Review cluster health, capacity reservations, model health, cleanup failures,
  and orphan resources before enabling broad ordering.

Start with [DEPLOYMENT.md](../DEPLOYMENT.md),
[deploy/multicluster/README.md](../deploy/multicluster/README.md), and
[provisioning-lifecycle.md](provisioning-lifecycle.md).

## Platform-developer onboarding

- Preserve request compatibility when adding typed fields or API responses.
- Add tests before implementation and keep the request, session, workshop, and
  cleanup contracts aligned.
- Treat `cluster_ref` as immutable after placement.
- Keep generated URLs cluster-aware and never use placeholder domains.
- Prefer capability discovery over catalog-specific conditionals.
- Update participant documentation whenever UI labels, access methods, catalog
  behavior, or lifecycle states change.

Architecture details are in [architecture.md](architecture.md), adapter behavior
in [adapters.md](adapters.md), and the repeatability contract in
[repeatable-process.md](repeatable-process.md).

## Getting help

Provide the smallest useful evidence bundle:

- persona and intended action;
- request, session, or workshop ID;
- tenant and catalog item;
- selected cluster, if shown;
- UTC or local timestamp with timezone;
- visible error and affected URL;
- whether retry or reclaim was attempted.

Never paste passwords, tokens, kubeconfigs, or unmasked MaaS keys into an issue
or chat.
