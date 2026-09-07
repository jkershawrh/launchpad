# Intel x Red Hat AI Partner Launchpad

Launchpad is an internal self-service lab platform running on the **Arena OpenShift cluster**. It provisions individual environments and multi-seat workshops, validates them before handoff, exposes participant access, and reclaims generated resources at the end of a session.

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

The portal and API are protected by OpenShift OAuth. The deployment is managed by the `launchpad` Argo CD Application using `deploy/launchpad/overlays/arena`.

## Supported user journeys

### Individual environment

Use **Request Environment → Individual Lab** to provision one catalog item for one user.

### Multi-seat workshop

Use **Request Environment → Multi-seat Workshop** to order one workshop containing 1–25 isolated participant seats. Launchpad performs a capacity preview before confirmation, provisions seats concurrently, requires collective endpoint stability before declaring the workshop ready, and supports failed-seat retry and group reclaim.

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
| `openshift-operators-workshop` | OpenShift AI Operator Workshop | Guided build |
| `rag-on-xeon` | RAG on Intel Xeon | Quick start |
| `smoke-test` | Smoke Test Demo | Quick start |

Catalog definitions live under `catalog/*/catalog-item.yaml`. The previous `guided-rag-on-xeon` item is deprecated; new workshop orders use the operator-focused experience.

Draft onboarding candidates are registered but intentionally hidden from the
order flow until runtime and live certification gates pass:

| ID | Name | Current gate |
|---|---|---|
| `agentops-observability` | AgentOps in Production: End-to-End Observability with Red Hat AI | Five internal seats are GREEN-live with isolated concurrent journeys and zero-residue normal/fault reclaim; 25-seat capacity, public access, and production Logging/TLS remain gated |
| `multi-agent-quickstart` | Build Multi-Agent AI Systems with Open Protocols | Active for internal orders up to 25 seats. One lab contains local, hands-on OpenShift, and advanced blueprint tracks. Track 2 runs a real workflow and has the learner apply, verify, and roll back an agent policy. Catalog v0.2.5 completed three consecutive GREEN-live 25-seat Arena runs with every hands-on journey and zero-residue reclaim proven. Optional advanced integrations, durable image supply, and public access remain gated |

## Architecture

```text
React portal
    │
    ▼
FastAPI provisioning service
    ├── catalog and policy validation
    ├── capacity/admission checks
    ├── per-session MaaS key
    └── persisted lifecycle state
    │
    ▼
Arena OpenShift adapters
    ├── namespace and namespace-scoped RBAC
    ├── workload/service/route deployment
    ├── per-seat Showroom Argo CD Application
    ├── readiness and route validation
    └── deterministic retry and cleanup
```

Launchpad has adapters for mock, local, direct OpenShift, and RHDP modes.
**Direct OpenShift mode is the deployed Arena path.** RHDP/AgnosticD integration
remains repository capability and a useful source contract for importing labs;
it is not the runtime control plane for the internal Intel deployment. The
AgentOps import analysis is in
[docs/agentops-rhdp-gap-analysis.md](docs/agentops-rhdp-gap-analysis.md).
The native Multi-Agent Quickstart intake and promotion gates are in
[docs/multi-agent-quickstart-import.md](docs/multi-agent-quickstart-import.md).

The approved September 17 internal event candidate is 25 Multi-Agent seats on
Arena, 25 Serve LLMs seats on Oberon, and 25 Building an AI Agent seats on
Brutus. Provisioning is staggered, every workshop stays wholly on its assigned
cluster, and all 75 environments then remain available concurrently. The exact
combined rehearsal and capacity gate are tracked in
[docs/september-17-agentic-three-workshop-readiness.md](docs/september-17-agentic-three-workshop-readiness.md).
Run 01 provisioned all 75 environments and reclaimed them without residue, but
is RED because Arena worker connectivity failed during participant probes.
Run 02 proved balanced placement and a healthy first 25-seat workshop, then
stopped on a backend OOM, a misleadingly Ready `rhgnr1`, and a late-seat
cancellation race. It also reached zero residue after targeted reconciliation.
The all-Arena runs remain immutable RED evidence. The next gate is a read-only
three-cluster preflight, followed by target-local certification on Oberon and
Brutus and an exact staggered fleet rehearsal. The event candidate is not yet
certified, and the remote targets remain disabled until their gates pass.

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
- Some older files in `docs/` describe the original RHDP/infra01 target. Files explicitly labeled **historical** are design references, not the Oberon production contract.
- Repository-wide lint currently includes pre-existing React purity errors in `BrandingContext.tsx` and `Fleet.tsx`.

For certified multi-seat behavior and the current visual release gate, see
[docs/oberon-workshop-readiness.md](docs/oberon-workshop-readiness.md). Deferred
performance, ETA, automation, and scale pathways are tracked in
[docs/next-iteration-roadmap.md](docs/next-iteration-roadmap.md). For adapter
behavior, see [docs/adapters.md](docs/adapters.md). StarGate, DeepField, and
GeoLux production-candidate paths are defined in
[docs/production-solution-pathways.md](docs/production-solution-pathways.md).
