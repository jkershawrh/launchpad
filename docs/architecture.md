# Architecture

## Platform Modules

| Module | Purpose | Stack |
|--------|---------|-------|
| **backend** | FastAPI app — domain models, adapters, services, API, storage | Python 3.11, Pydantic, PostgreSQL |
| **frontend** | Partner portal — catalog browsing, lab requests, session detail | React, Vite, Tailwind |
| **admin** | Admin dashboard — sessions by tenant, showback summaries, failed validations | React, Vite, Tailwind |
| **demos** | Inference gateway, Overdrive engine, quickstarts, PoCs, containers | Python, podman-compose, Helm |

## Adapter Pattern

The platform never hardcodes external systems into core logic. Every external integration is an adapter behind a Protocol interface.

| Adapter tier | When to use | Examples |
|-------------|-------------|----------|
| **mock** | Unit/integration tests, local demo | MockCatalogAdapter, MockPoolAdapter |
| **local** | Podman-compose on developer laptop | LocalSandboxProvisioner, local cleanup |
| **openshift** | Live OCP cluster via Kubernetes API + oc CLI | OpenShiftSandboxProvisioner, namespace/RBAC/quota creation |
| **sandbox** | Pod-based environments with SSH/Jupyter/VS Code access | SandboxProfile with stack levels (minimal, ai_dev, full_redhat_ai) |

See [adapters.md](adapters.md) for the full interface catalog.

## Domain Models

| Model | Role |
|-------|------|
| **Tenant** | Company, partner, internal team, or client. Carries branding, quota defaults, TTL. |
| **CatalogItem** | Reusable lab/demo definition. Category: quick_start, guided_build, open_sandbox. |
| **LabRequest** | User request for a catalog item. Evaluated against constraints before acceptance. |
| **LabSession** | Provisioned lab environment. Tracks namespace, URLs, status, validation, showback. |
| **ProvisioningPlan** | Generated steps to stand up a session — namespace, quota, RBAC, deploy, gateway. |
| **HardwareProfile** | Hardware requirements — Xeon, Gaudi endpoint, Gaudi direct, mixed. |
| **QuotaProfile** | Resource limits — CPU, memory, storage, pods, routes, Gaudi access, TTL max. |
| **BrandingProfile** | Visual identity — title, colors, logo, theme (default, cockpit_dark, partner_light). |
| **ShowbackRecord** | Usage tracking — duration, CPU, memory, storage, Gaudi, tokens, model requests. |
| **ValidationResult** | Per-check outcome — pass, fail, warn, skipped — with evidence. |

## Provisioning Flow

```
submit request
  -> evaluate constraints (allowed / warn / blocked)
  -> accept or reject
  -> check pool capacity + reserve
  -> generate provisioning plan
  -> execute plan (create namespace, apply quota, deploy app, configure gateway)
  -> transition to VALIDATING
  -> run validation checks
  -> READY (all pass) or VALIDATION_FAILED
  -> ACTIVE (user opens lab)
  -> EXPIRED (TTL)
  -> RESETTING -> RECLAIMED
```

Every session gets a per-session MaaS API key (`sk-launchpad-*`) for model access.

## Tenant Gateway Architecture

Each tenant gets a shared inference gateway instance. Multiple demos within the same tenant share one gateway namespace. When the last demo for a tenant is reclaimed, the gateway namespace is cleaned up.

The gateway routes requests by task type and model size:
- Embeddings, classification, reranking -> OpenVINO on Xeon 6
- Small completions (<= 3B params) -> vLLM on Xeon 6
- Large completions (> 3B params) -> vLLM on Gaudi
- Batch generation -> Gaudi

Each demo gets a filtered frontend view while sharing backend inference capacity.

## MaaS Integration

The gateway exposes a LiteLLM-compatible `/v1/chat/completions` endpoint. 11 models are served across three backends (OpenVINO-CPU, vLLM-CPU, vLLM-Gaudi). Cost-per-token tracking feeds into showback records.
