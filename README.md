# Intel x Red Hat AI Partner Launchpad

Launchpad is an internal self-service lab platform running on the **Oberon OpenShift cluster**. It provisions individual environments and multi-seat workshops, validates them before handoff, exposes participant access, and reclaims generated resources at the end of a session.

## Current deployment

| Surface | URL |
|---|---|
| Partner portal | <https://launchpad.apps.oberon.fm2aihpcsed.com> |
| Admin dashboard | <https://launchpad-admin.apps.oberon.fm2aihpcsed.com> |
| Backend API | <https://launchpad-api.apps.oberon.fm2aihpcsed.com> |

The portal and API are protected by OpenShift OAuth. The deployment is managed by the `launchpad` Argo CD Application using `deploy/launchpad/overlays/oberon`.

## Supported user journeys

### Individual environment

Use **Request Environment → Individual Lab** to provision one catalog item for one user.

### Multi-seat workshop

Use **Request Environment → Multi-seat Workshop** to order one workshop containing 1–25 isolated participant seats. Launchpad performs a capacity preview before confirmation, provisions seats concurrently, requires collective endpoint stability before declaring the workshop ready, and supports failed-seat retry and group reclaim.

### OpenShift Developer Sandbox

The `ai-sandbox` catalog item is OpenShift-first. Its primary access is the real OpenShift Console scoped to the generated namespace, with Web Terminal and browser IDE access where available. The requester receives the namespace-level `edit` role; Launchpad does not grant cluster-admin. Jupyter is not a default access method.

The shared Oberon platform currently provides Red Hat OpenShift AI, Serverless, Service Mesh, cluster observability, Argo CD, and Intel device plugins. These operators are centrally managed; a sandbox order does not install cluster-wide operators.

## Active file-backed catalog

| ID | Name | Category |
|---|---|---|
| `ai-sandbox` | OpenShift Developer Sandbox | Open sandbox |
| `cpu-inference-serving` | LLM CPU Serving on Xeon | Quick start |
| `openshift-operators-workshop` | OpenShift AI Operator Workshop | Guided build |
| `rag-on-xeon` | RAG on Intel Xeon | Quick start |
| `smoke-test` | Smoke Test Demo | Quick start |

Catalog definitions live under `catalog/*/catalog-item.yaml`. The previous `guided-rag-on-xeon` item is deprecated; new workshop orders use the operator-focused experience.

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
Oberon OpenShift adapters
    ├── namespace and namespace-scoped RBAC
    ├── workload/service/route deployment
    ├── per-seat Showroom Argo CD Application
    ├── readiness and route validation
    └── deterministic retry and cleanup
```

Launchpad has adapters for mock, local, direct OpenShift, and RHDP modes. **Direct OpenShift mode is the deployed Oberon path.** RHDP/AgnosticD integration remains repository capability and historical design context; it is not required for the internal Intel deployment.

## Repository layout

```text
backend/       FastAPI API, domain models, services, and adapters
frontend/      Partner portal
admin/         Internal operations UI
catalog/       Active file-backed catalog definitions
content/       Antora/AsciiDoc Showroom content
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

Use an explicit Oberon context for every cluster command; do not change the current kubeconfig context:

```bash
oc --context='default/api-oberon-fm2aihpcsed-com:6443/kube:admin' ...
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
behavior, see [docs/adapters.md](docs/adapters.md).
