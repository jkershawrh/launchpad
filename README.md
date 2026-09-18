# Intel x Red Hat AI Partner Launchpad

Launchpad is an internal self-service lab platform whose current pilot control
plane runs on **Arena** and whose participant workloads run on certified
execution clusters. It provisions individual environments and multi-seat
workshops, validates them before handoff, exposes one participant entry point,
and reclaims generated resources from the persisted target cluster.

Its target operating model is self-service at both layers: users and CIs can
request or contribute governed experiences, while the platform detects and
recovers from known low-risk failures through evidence-gated automation. Novel,
security-sensitive, cluster-scoped, and high-impact actions remain human
approved. See the
[self-service and auto-remediation operating model](docs/self-service-and-autoremediation.md).

Public passwordless participant access is implemented behind a fail-closed
release gate. See [public lab access](docs/PUBLIC_ACCESS.md) for persona flows,
infrastructure prerequisites, contracts and certification evidence.

## Start here

New participants, instructors, content integrators (CIs), tenant owners,
platform operators, and developers should begin with the
[persona onboarding guide](docs/persona-onboarding.md). It defines access
boundaries, first-use workflows, the CI delivery contract, testing and
certification expectations, and the evidence to provide when requesting help.
New catalog experiences use the repository-native
[catalog onboarding pipeline](docs/catalog-onboarding.md) so source validation,
catalog generation, Antora builds, and evidence receipts are repeatable.
An existing quickstart Git repository can now be discovered into a fail-closed
intake before entering the same review and 1/5/25 certification pipeline.

Pilot presenters and operators should also use the
[demo walkthrough](docs/presenter-demo-walkthrough.md),
[ecosystem architecture and product roadmap](docs/ecosystem-architecture-roadmap.md),
the [product delivery roadmap](docs/product-delivery-roadmap.md),
the [clickable product roadmap dashboard](docs/product-roadmap-dashboard.html),
the [pilot issue and feature register](docs/pilot-issue-feature-register-20260917.md),
the [active-seat inventory and reclaim observation plan](docs/active-seat-inventory-20260917.md),
the [StarGate product telemetry contract](docs/stargate-product-telemetry-contract.md),
the [presentation source](docs/presentations/launchpad-ecosystem-demo.md),
the [template-based PowerPoint deck](docs/presentations/launchpad-ecosystem-demo-gcl-template.pptx), and
[support runbook](docs/support-runbook.md). The current TDD/EDD/CDD/BDD/CBT
status is recorded in the
[ecosystem enablement proof matrix](docs/ecosystem-enablement-proof-matrix.md).
The portable
[ecosystem playbooks](deploy/ecosystem/README.md) wrap the approved deployment,
remote registration, validation, and group-reclaim paths without changing the
workstation's Kubernetes context.
Documentation precedence and the boundary between current contracts and dated
historical evidence are defined in the
[documentation authority and drift policy](docs/documentation-authority.md).

Quick paths:

- **Participant:** open the assigned ready session, then use its Visual Guide
  and Live Workspace.
- **Instructor:** order one multi-seat workshop, verify capacity, wait for every
  seat to become ready, distribute seat-specific links, and reclaim after use.
- **Content integrator:** keep the catalog definition, Antora/AsciiDoc Showroom
  content, tests, and deployable resources in this repository; submit them for
  review and certification.
- **Operator:** use the admin dashboard and cluster-aware runbooks; production
  promotion and shared Operator/model management are administrative actions.

## Current deployment

| Surface | URL |
|---|---|
| Partner portal | <https://launchpad.apps.arena.fm2aihpcsed.com> |
| Admin dashboard | <https://launchpad-admin.apps.arena.fm2aihpcsed.com> |
| Backend API | <https://launchpad-api.apps.arena.fm2aihpcsed.com> |
| Public participant gateway | <https://labs.smg-helix.ai> |

The portal and API are protected by OpenShift OAuth. The deployment is managed by the `launchpad` Argo CD Application using `deploy/launchpad/overlays/arena`.

### Lifecycle HA and Flightpath DR

The repository now contains a feature-gated durable lifecycle worker design for
provisioning, validation, TTL, reconciliation, and reclaim. PostgreSQL-backed
leases and monotonically increasing fencing tokens keep one worker responsible
for a session or workshop, while the operations view reports queue health,
retries, takeovers, and stuck cleanup. The base remains disabled; the candidate
Arena activation shape is `deploy/launchpad/overlays/arena-ha-pilot`.

Flightpath is registered only as an inactive control-plane DR standby. Its
overlay renders all Deployments at zero replicas and suspends CronJobs so it
cannot become a second writer by accident. Promotion requires a hard Arena
fence, verified data/secret restoration, and staged validation. See the
[control-plane DR roadmap](docs/control-plane-dr-roadmap.md), the
[Flightpath DR runbook](docs/flightpath-dr-runbook.md), and the current
[HA/DR certification matrix](docs/ha-dr-certification-20260908.md). Neither
overlay has been applied to a live cluster by this change.

## Supported user journeys

### Individual environment

Use **Request Environment → Individual Lab** to provision one catalog item for one user.

### Multi-seat workshop

Use **Request Environment → Multi-seat Workshop** to order one workshop of
isolated participant seats. The permitted count is the measured limit for the
selected catalog × cluster × exposure policy, not one platform-wide constant.
Launchpad performs a capacity preview and aggregate reservation before
confirmation, provisions seats in bounded waves, requires collective functional
stability before declaring the workshop ready, and supports failed-seat retry
and group reclaim.

### OpenShift Developer Sandbox

The `ai-sandbox` catalog item is OpenShift-first. Its primary access is the real OpenShift Console scoped to the generated namespace, with Web Terminal and browser IDE access where available. The requester receives the namespace-level `edit` role; Launchpad does not grant cluster-admin. Jupyter is not a default access method.

The shared Arena platform provides the centrally managed OpenShift capabilities used by catalog experiences. A sandbox or guided lab order receives namespace-scoped access and does not install cluster-wide operators.

The request form shows the live healthy model inventory and permits multiple
model selections. Models remain centrally served behind LiteLLM; the sandbox
receives scoped API access and does not load model weights into its pod.

## Active file-backed catalog

| ID | Name | Category |
|---|---|---|
| `ai-sandbox` | OpenShift Developer Sandbox | Open sandbox |
| `cpu-inference-serving` | LLM CPU Serving on Xeon | Quick start |
| `intel-llm-cpu-serving` | Intel AI Quickstart: Serve LLMs on Intel Xeon CPUs | Guided build |
| `intel-llm-tool-calling` | Intel AI Quickstart: LLM Tool Calling on Intel | Guided build |
| `intel-xeon6-agent-201` | Intel Xeon 6 201: Building an AI Agent | Guided build |
| `multi-agent-quickstart` | Build Multi-Agent AI Systems with Open Protocols | Guided build |
| `openshift-operators-workshop` | OpenShift AI Operator Workshop | Guided build |
| `rag-on-xeon` | RAG on Intel Xeon | Quick start |
| `smoke-test` | Smoke Test Demo | Quick start |

Catalog definitions live under `catalog/*/catalog-item.yaml`. The previous `guided-rag-on-xeon` item is deprecated; new workshop orders use the operator-focused experience.

Draft onboarding candidates are registered but intentionally hidden from the
order flow until runtime and live certification gates pass:

| ID | Name | Current gate |
|---|---|---|
| `agentops-observability` | AgentOps in Production: End-to-End Observability with Red Hat AI | Five internal seats are GREEN-live with isolated concurrent journeys and zero-residue normal/fault reclaim; 25-seat capacity, public access, and production Logging/TLS remain gated |

`multi-agent-quickstart` has a certified baseline and may use a larger
event-specific ceiling only where that exact execution target and public-access
pairing has retained proof. One lab contains local, hands-on OpenShift, and
advanced blueprint tracks. Optional advanced integrations and durable artifact
supply remain later hardening work; dated September readiness documents remain
historical evidence rather than the current product contract.

## Architecture

```text
stable participant/requester edge
    │
    ▼
Launchpad control plane
    ├── catalog, identity, policy and lifecycle state
    ├── whole-workshop placement and capacity reservation
    ├── durable provision/reclaim workers and evidence
    └── GitOps, audit, usage and remediation coordination
    │
    ├──► certified execution-cluster fleet
    │       namespaces, Showroom, lab workloads and Operators
    ├──► shared AI-serving plane
    │       private model gateway, model pools and usage attribution
    └──► durable artifact supply
            signed immutable digests in HA registry and mirrors
```

Launchpad has adapters for mock, local, direct OpenShift, and RHDP modes.
**Direct OpenShift mode is the deployed Arena path.** RHDP/AgnosticD integration
remains repository capability and a useful source contract for importing labs;
it is not the runtime control plane for the internal Intel deployment. The
AgentOps import analysis is in
[docs/agentops-rhdp-gap-analysis.md](docs/agentops-rhdp-gap-analysis.md).
The native Multi-Agent Quickstart intake and promotion gates are in
[docs/multi-agent-quickstart-import.md](docs/multi-agent-quickstart-import.md).

The September 17 live pilot uses three participant waves. Each wave contains
30 Serve LLMs seats, 30 Building an AI Agent seats, and 30 Multi-Agent seats.
Provisioning is staggered, every workshop stays wholly on its assigned cluster,
and participants use one Launchpad entry point even when execution targets
differ. The original 25-seat candidate and its failures remain recorded in
[docs/september-17-agentic-three-workshop-readiness.md](docs/september-17-agentic-three-workshop-readiness.md).
The durable lifecycle queue now enforces one active workshop-provision job
fleet-wide. Organizers may submit later orders, but they remain queued until
the preceding workshop finishes; reclaim and individual-session lifecycle jobs
remain eligible.
Historical September rehearsals remain evidence for the failure modes they
captured; they do not override current live status. Public DNS/TLS and OIDC use
the permanent `labs.smg-helix.ai` named tunnel. Current event readiness is
decided by the active workshop records, live functional probes, model health,
participant access, and the retained release evidence. The pilot matrix,
rubric, and manual acceptance boundary are in
[docs/september-17-pilot-status-20260908.md](docs/september-17-pilot-status-20260908.md).

## Repository layout

```text
backend/       FastAPI API, domain models, services, and adapters
frontend/      Partner portal
admin/         Internal operations UI
catalog/       Active file-backed catalog definitions
certification/ Declarative 1/5/25-seat proof contracts
content/       Antora/AsciiDoc Showroom content
content-*/      Catalog-specific Antora/AsciiDoc Showroom content
demos/         Demo frontend, gateway, and sandbox image
deploy/        Kustomize, build, and optional RHDP/AgnosticV assets
docs/          Current runbooks plus historical design documents
```

Generated CI receipts are uploaded as workflow artifacts and are not committed.
Historical proof remains immutable until its hash and reference chain has been
migrated deliberately. See the
[repository hygiene policy](docs/repository-hygiene.md) before moving or
deleting catalogs, evidence, demo assets, or historical documents.

## Development and verification

```bash
.venv/bin/pytest -q backend/tests

cd frontend
npm test -- --run
npm run build
```

New catalog experiences must include tests for their schema, request contract,
provisioning plan, functional validation, Showroom journey, and deterministic
cleanup. Follow the staged CI checklist in
[docs/persona-onboarding.md](docs/persona-onboarding.md#content-integrator-ci-onboarding)
and declare new sources through
[docs/catalog-onboarding.md](docs/catalog-onboarding.md).

Use the reusable certification runner to prove the same lifecycle for every
onboarded catalog item. Planning is read-only; `run` creates one workshop order,
waits for every seat, executes the lab-specific probe concurrently, reclaims the
order, and writes sanitized JSON plus a SHA-256 manifest:

```bash
.venv/bin/python scripts/catalog_certification.py plan \
  certification/catalog/<catalog-id>.yaml --seats 25

KUBECONFIG=/path/to/arena-kubeconfig \
LAUNCHPAD_ADMIN_API_KEY='set-outside-git' \
.venv/bin/python scripts/catalog_certification.py run \
  certification/catalog/<catalog-id>.yaml \
  --seats 25 \
  --api-base-url https://launchpad-api.apps.arena.fm2aihpcsed.com \
  --tenant-id <certification-tenant> \
  --owner-id <operator> \
  --run-id <unique-proof-run>
```

Never put the API key in the command line, contract, logs, or evidence.

Use Arena's dedicated kubeconfig for every cluster command; do not change the current kubeconfig context:

```bash
KUBECONFIG=/Users/jkershaw/.kube/config-arena oc ...
```

## Current limitations

- Existing Guided RAG sessions retain their original content; new orders use the OpenShift AI Operator Workshop.
- Operator availability is cluster-wide and centrally managed; catalog items should detect and use installed capabilities rather than install an Operator per participant seat.
- Some older files in `docs/` describe the original RHDP/infra01 target. Files explicitly labeled **historical** are design references, not the current Intel deployment contract.
- Repository-wide lint currently includes pre-existing React purity errors in `BrandingContext.tsx` and `Fleet.tsx`.

For the current multi-seat event behavior and release gate, see
[docs/september-17-agentic-three-workshop-readiness.md](docs/september-17-agentic-three-workshop-readiness.md). Deferred
performance, ETA, automation, and scale pathways are tracked in
[docs/next-iteration-roadmap.md](docs/next-iteration-roadmap.md). For adapter
behavior, see [docs/adapters.md](docs/adapters.md). StarGate, DeepField, and
GeoLux production-candidate paths are defined in
[docs/production-solution-pathways.md](docs/production-solution-pathways.md).
