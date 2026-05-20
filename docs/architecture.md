# Architecture

## Platform Modules

| Module | Purpose | Stack |
|--------|---------|-------|
| **backend** | FastAPI app — domain models, adapters, services, API, storage | Python, Pydantic, PostgreSQL |
| **frontend** | Partner portal — catalog browsing, lab requests, session detail | React, Vite, Tailwind |
| **admin** | Admin dashboard — sessions, tenants, catalog CRUD, system status | React, Vite, Tailwind |
| **demos/frontend** | Demo frontend — runtime page filtering, 10 demo pages | React, Vite, Tailwind |
| **demos/gateway** | Inference gateway — model routing policy across Intel hardware | Python, FastAPI |
| **content** | Showroom lab content — step-by-step walkthroughs for each demo | Antora, AsciiDoc |
| **tenant/bootstrap** | Helm chart deployed per-user by ArgoCD | Helm |
| **deploy/agnosticv** | RHDP catalog item configs — cluster + tenant definitions | AgnosticV YAML |
| **deploy/launchpad** | Kustomize manifests for the Launchpad platform itself | Kustomize |

## Adapter Pattern

The platform never hardcodes external systems into core logic. Every external integration is an adapter behind a Protocol interface.

| Adapter tier | `LAUNCHPAD_MODE` | When to use |
|-------------|-----------------|-------------|
| **mock** | `mock` (default) | Unit/integration tests, local demo |
| **local** | `local` | Podman-compose on developer laptop |
| **openshift** | `openshift` | Direct deployment on a live OCP cluster via Kubernetes API |
| **rhdp** | `rhdp` | Red Hat Demo Platform — Sandbox API for cluster pool, AgnosticD for deployment |

See [adapters.md](adapters.md) for the full interface catalog and per-tier details.

## Domain Models

| Model | Role |
|-------|------|
| **Tenant** | Company, partner, internal team, or client. Carries branding, quota defaults, TTL. |
| **CatalogItem** | Reusable lab/demo definition. Category: quick_start, guided_build, open_sandbox. 25 items in catalog. |
| **LabRequest** | User request for a catalog item. Evaluated against constraints before acceptance. |
| **LabSession** | Provisioned lab environment. Tracks namespace, cluster_ref, URLs, status, validation, showback. |
| **ProvisioningPlan** | Generated steps to stand up a session — namespace, quota, RBAC, deploy, gateway. |
| **HardwareProfile** | Hardware requirements — Xeon, Gaudi endpoint, Gaudi direct, mixed. |
| **QuotaProfile** | Resource limits — CPU, memory, storage, pods, routes, Gaudi access, TTL max. |
| **BrandingProfile** | Visual identity — title, colors, logo, theme (default, cockpit_dark, partner_light). |
| **ShowbackRecord** | Usage tracking — duration, CPU, memory, storage, Gaudi, tokens, model requests. |
| **ValidationResult** | Per-check outcome — pass, fail, warn, skipped — with evidence. |

## Provisioning Flow

### Direct Mode (mock / local / openshift)

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

### RHDP Mode

```
submit request
  -> evaluate constraints
  -> accept or reject
  -> Sandbox API: claim namespace on shared CNV cluster
  -> generate provisioning plan (references AgnosticV tenant config)
  -> execute plan (AgnosticD deploys via ArgoCD)
  -> populate cluster_ref on session
  -> transition to VALIDATING
  -> validate sandbox placement + namespace
  -> READY -> ACTIVE
  -> RECLAIMED (Sandbox API releases placement)
```

Every session gets a per-session MaaS API key (`sk-launchpad-*`) for model access.
Session limits enforce max 2 active per user, 5 per tenant.

## RHDP Integration Architecture

```
User -> RHDP Catalog (demo.redhat.com) -> Sandbox API -> CNV cluster namespace
                                                              |
                                                         AgnosticD deploys:
                                                         - Keycloak user
                                                         - Namespace + quotas
                                                         - LiteLLM virtual key
                                                         - ArgoCD -> tenant/bootstrap Helm chart
                                                         - Showroom lab UI
```

The Sandbox API manages a fleet of 10 CNV clusters. Each cluster is registered with capability annotations (intel, gaudi, xeon6, etc.). Demo configs declare required capabilities via `cloud_selector`, and the Sandbox API selects a matching cluster.

## Tenant Gateway Architecture

In RHDP mode, each tenant gets their own gateway instance in their namespace (deployed by the tenant Helm chart). The gateway connects to LiteMaaS via the tenant's LiteLLM virtual key.

In OpenShift mode, tenants share a gateway namespace (`launchpad-gw-{tenant_id}`). Multiple demos within the same tenant share one gateway. When the last demo for a tenant is reclaimed, the gateway namespace is cleaned up.

The gateway routes requests by task type and model size:
- Embeddings, classification, reranking -> Xeon 6
- Small completions (<= 3B params) -> Xeon 6
- Large completions (> 3B params) -> Gaudi 3
- Batch generation -> Gaudi 3

Each demo gets a filtered frontend view while sharing backend inference capacity.

## MaaS Integration

The gateway exposes a LiteLLM-compatible `/v1/chat/completions` endpoint. 5 models are currently served on the ocp-rac-maas cluster via KServe on OpenShift AI:

| Model | Hardware | Gaudi Cards |
|-------|----------|-------------|
| Granite 3.2 8B Instruct | Gaudi 3 | 4 |
| Llama 3.1 70B | CPU (llama.cpp) | — |
| DeepSeek R1 Distill Qwen 14B | Gaudi 3 | 4 |
| Microsoft Phi-4 | Gaudi 3 | 2 |
| Qwen3 14B | Gaudi 3 | 8 (2 replicas) |

Per-tenant LiteLLM virtual keys provide model access control, rate limiting, and usage tracking. Each demo gets keys scoped to only the models it needs (1-5 models depending on demo).
