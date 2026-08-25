# Architecture

## Platform Modules

| Module | Purpose | Stack |
|--------|---------|-------|
| **backend** | FastAPI app — domain models, adapters, services, API, storage | Python, Pydantic, PostgreSQL |
| **frontend** | Partner portal — catalog browsing, lab requests, session detail | React, Vite, Tailwind |
| **admin** | Admin dashboard — sessions, tenants, catalog CRUD, system status | React, Vite, Tailwind |
| **demos/frontend** | Demo frontend — 18+ pages including FleetIntelligence dashboard | React, Vite, PatternFly |
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

### Core Models (`domain/models.py`)

| Model | Role |
|-------|------|
| **Tenant** | Company, partner, internal team, or client. Carries branding, quota defaults, TTL. |
| **CatalogItem** | Reusable lab/demo definition. Category: quick_start, guided_build, open_sandbox. Five active file-backed items currently ship in `catalog/`. |
| **LabRequest** | User request for a catalog item. Evaluated against constraints before acceptance. |
| **LabSession** | Provisioned lab environment. Tracks namespace, cluster_ref, URLs, status, validation, showback. |
| **ProvisioningPlan** | Generated steps to stand up a session — namespace, quota, RBAC, deploy, gateway. |
| **HardwareProfile** | Hardware requirements — Xeon, Gaudi endpoint, Gaudi direct, mixed. |
| **QuotaProfile** | Resource limits — CPU, memory, storage, pods, routes, Gaudi access, TTL max. |
| **BrandingProfile** | Visual identity — title, colors, logo, theme (default, cockpit_dark, partner_light). |
| **ShowbackRecord** | Usage tracking — duration, CPU, memory, storage, Gaudi, tokens, model requests. |
| **ValidationResult** | Per-check outcome — pass, fail, warn, skipped — with evidence. |

### Intelligence Models

| Model | File | Role |
|-------|------|------|
| **WorkloadProfile** | `domain/workload.py` | Workload classification — type (CPU/GPU/training/RAG/agent/mixed/lightweight), compute/memory intensity, GPU mode, I/O pattern, confidence |
| **HardwareMatch** | `domain/workload.py` | Scored hardware recommendation with reasons |
| **ClusterCapacity** | `domain/placement.py` | Per-cluster capacity score, CPU utilization, GPU availability, health status |
| **PlacementRecommendation** | `domain/placement.py` | Recommended cluster with score, reasoning, source (cache/live/none), fallback flag |
| **PlacementDecision** | `domain/placement.py` | Audit record of the placement choice made for a request |
| **ProvisioningOutcome** | `domain/feedback.py` | Success/failure record per session — cluster, hardware, latency, validation result |
| **FeedbackSummary** | `domain/feedback.py` | Aggregated success rate, avg latency, recommendation (preferred/acceptable/avoid) per cluster×catalog×hardware |
| **OrchestrationDecision** | `domain/orchestration.py` | Full decision record — workload profile, cluster, hardware, quota, confidence, rationale, signals used |
| **DeepFieldSignal** | `domain/orchestration.py` | Fleet health metric — cluster, type (cpu_util, gpu_util, error_rate), value, threshold, status |
| **HealthAlert** | `domain/orchestration.py` | Proactive alert — cluster, severity, recommended action, triggering signals |

## Intelligence Layer

### Services

| Service | Purpose |
|---------|---------|
| **PlacementService** | Queries StarGate for cluster capacity scores, caches locally (120s TTL), recommends healthiest cluster. Filters by feedback avoid-list when FeedbackTracker is available. |
| **WorkloadClassifier** | Rule-based classification from catalog metadata (`cpu_only`, `required_capabilities`, `default_hardware_profile`). Returns scored hardware matches and right-sized quotas. |
| **FeedbackTracker** | Records ProvisioningOutcome after each validation. Computes success rates per cluster×catalog×hardware. Flags combinations with <30% success rate (>= 5 samples) as "avoid." Persists to PostgreSQL. |
| **OrchestrationBrain** | Coordinates all signals: classify workload → get capacity → get fleet signals → check feedback → compute blended score → generate rationale. Confidence scales with signal diversity. |

### Decision Flow

```
LabRequest arrives
    │
    ├── User specified hardware+quota? → use as-is (override)
    │
    ├── OrchestrationBrain available?
    │   └── brain.decide(request, catalog_item)
    │       ├── WorkloadClassifier.classify() → WorkloadProfile
    │       ├── PlacementService cache + DeepField signals → scored clusters
    │       ├── FeedbackTracker.should_avoid() → filter bad combos
    │       └── → OrchestrationDecision (stored in session resources)
    │
    ├── WorkloadClassifier only?
    │   └── classify → match_hardware → top match
    │
    └── Nothing? → static fallback (catalog default → "xeon-basic")
```

### Graceful Degradation

Every intelligence component fails open:

| Condition | Behavior |
|-----------|----------|
| Brain raises exception | Falls through to classifier, then static |
| StarGate unreachable | Placement returns fallback, pool picks cluster |
| DeepField unreachable | Signals excluded from scoring, decision continues |
| FeedbackTracker empty | No avoid-list filtering, all clusters eligible |
| All external systems down | Provisions exactly as a static system would |

## Provisioning Flow

### Provisioning Flow (all modes)

```
submit request
  -> evaluate constraints (StarGate pre-flight if configured)
  -> accept or reject
  -> _resolve_hardware():
       brain.decide() OR classifier.classify() OR static fallback
  -> _get_placement_recommendation():
       PlacementService.recommend_cluster() with feedback filtering
  -> pool.reserve(preferred_cluster=recommendation)
  -> generate provisioning plan
  -> execute plan
  -> transition to VALIDATING
  -> run validation checks
  -> _record_feedback(success or failure)
  -> READY -> ACTIVE -> RECLAIMED
```

In RHDP mode, `pool.reserve()` calls the Sandbox API with `preferred_cluster` in the cloud selector. In mock/local/openshift modes, the placement recommendation is advisory.

Every session gets a per-session MaaS API key (`sk-launchpad-*`) for model access.
Session limits enforce max 2 active per user, 5 per tenant.
OrchestrationDecision is stored in session `resources["decision"]` for frontend retrieval.

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

The gateway exposes a LiteLLM-compatible `/v1/chat/completions` endpoint. 5 models are served via KServe on OpenShift AI:

| Model | Hardware | Gaudi Cards |
|-------|----------|-------------|
| Granite 3.2 8B Instruct | Gaudi 3 | 4 |
| Llama 3.1 70B | CPU (llama.cpp) | — |
| DeepSeek R1 Distill Qwen 14B | Gaudi 3 | 4 |
| Microsoft Phi-4 | Gaudi 3 | 2 |
| Qwen3 14B | Gaudi 3 | 8 (2 replicas) |

Per-tenant LiteLLM virtual keys provide model access control, rate limiting, and usage tracking. Each demo gets keys scoped to only the models it needs (1-5 models depending on demo).
