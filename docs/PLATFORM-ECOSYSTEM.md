# Intel x Red Hat AI Platform Ecosystem

## Overview

Four applications form the Intel x Red Hat AI demo and operations platform. Three are core products that integrate via webhook events. A fourth is the sandbox where new features are built and tested before graduating to production.

```
                         +-------------------+
                         |     DeepField     |   OBSERVABILITY PLANE
                         | Fleet signal intel|   Watches N clusters
                         | 12 nano-agents    |   Demo/sim = onboarding ramp
                         | Live monitoring   |   Live monitoring = main objective
                         +--------+----------+
                                  |
                       monitors clusters that
                       Launchpad provisions on
                                  |
   +------------------+    +------v--------------+
   |    StarGate      |    |     Launchpad       |   PROVISIONING + DEMO PLANE
   | Rubric evaluator |<-->| 17-state lifecycle  |   Self-service AI labs on
   | Evidence bundles |    | 10 demos + 7 QS     |   shared OpenShift with
   | Failure classes  |    | Inference gateway   |   Intel Gaudi 3 / Xeon 6
   | HITL proposals   |    | Workshop batching   |
   +------------------+    +----------+----------+
                                      |
                           code graduates from
                                      |
                         +------------v-------+
                         | Partnership Demo   |   SANDBOX / INCUBATOR
                         | R&D proving ground |   Own site, own identity
                         | Overdrive engine   |   Features tested here first
                         | Research Agent     |   Copy-paste → Launchpad
                         +--------------------+
```

---

## The Four Products

### Launchpad — Provisioning + Demo Plane

Self-service AI demo platform. Partners and customers order demos from the RHDP catalog, get isolated environments with real inference on Intel Gaudi 3 and Xeon 6, and everything cleans up automatically.

- **17-state lifecycle machine** — request → provision → validate → ready → activate → reclaim
- **25 catalog items** — 10 custom Intel demos, 7 official quickstarts, 4 sandboxes, 4 originals
- **3 provisioning modes** — self-service, workshops (40+ users), persistent
- **RHDP native** — Sandbox API, AgnosticV catalog, ArgoCD Helm charts, Showroom content
- **Repo:** https://github.com/rhpds/launchpad

### StarGate — Validation Plane

Evidence-driven rubric evaluation for demo environment correctness. Deterministic YAML rubrics catch 80%+ of failures. LLM is called only for novel/unclassified failures with full context.

- **Runs → Stages → Evidence** pipeline for structured validation
- **YAML rubrics** define what "correct" looks like per stage
- **Failure classification** maps conditions to known failure classes
- **HITL workflow** — AI proposes rubric changes, humans approve
- **Repo:** local (deployment parked for now)

### DeepField — Observability Plane

Fleet-scale OpenShift signal intelligence. One Intel inference cluster monitors N OpenShift clusters because deterministic nano-agent filters compress telemetry so only a tiny fraction requires expensive LLM reasoning.

- **16,666:1 compression ratio** — 10M raw signals → 600 reasoning tasks
- **12 nano-agent filters** — deterministic, no LLM, fast
- **Correlation engine** — namespace, cluster, cross-cluster grouping
- **Inference routing** — phi4 fast / qwen3 general / deepseek reasoning
- **Repo:** https://github.com/rhpds/deepfield

### Partnership Demo — Sandbox / Incubator

The R&D proving ground for inference gateway features. Stakeholders know this as the "Intel-Red Hat AI Inference Platform" demo. When features are proven here, they graduate to Launchpad via copy-paste.

- **Hardware-aware routing** — Eco/Performance/Overdrive lanes
- **Governance layer** — risk assessment, approval workflows
- **Cost analytics** — per-backend cost breakdown, latency percentiles
- **Research Agent** — multi-step RAG with governance
- **Repo:** https://github.com/rhpds/red-hat-intel-partnership-demo

---

## Integration Architecture

### Event Flow

All three core products communicate via webhook push. Each product can deploy independently. When co-deployed, they form a provision-validate-monitor control loop.

```
LAUNCHPAD                          STARGATE                         DEEPFIELD
=========                          ========                         =========

Session lifecycle events ------>  POST /integration/events    
  (provisioned, ready,              |                          
   active, failed,                   +-- evaluates rubrics     
   cleanup_failed, reclaimed)        +-- classifies failures   
                                     |                         
                                  Evaluation results -------->  POST /integration/events
                                    (stage passed/failed,         |
                                     failure classified)          +-- nano-agent filters
                                                                  +-- correlates signals
                                                                  +-- LLM RCA if needed
                                                                  |
Pre-flight check -------------->  GET /integration/evaluate      
  (before provisioning)              |                           
  response: allowed/blocked          +-- rubric evaluation       

                                  Cleanup result -------------->  
                                    (remediation outcome)         
Cleanup callback <--------------  POST /callbacks/cleanup-result  

Session lifecycle events ---------------------------------->  POST /integration/events
  (same events, also sent                                       |
   to DeepField directly)                                       +-- launchpad_session agent
                                                                +-- correlates with cluster signals

Remediation callback <--------------------------------------  POST /callbacks/remediation
  (session reset/reclaim)                                       (when nano-agent escalates)
```

### Control Loop

When all three are deployed together, they form a closed feedback loop:

```
Launchpad PROVISIONS environment
    |
    +---> StarGate VALIDATES it (rubric evaluation)
    |         |
    |         +---> (pass) Launchpad → ACTIVE
    |         +---> (fail) StarGate classifies failure
    |                   |
    |                   +---> DeepField receives signal, correlates
    |                   +---> DeepField suggests remediation
    |                   +---> Launchpad RESETS and retries
    |
    +---> DeepField MONITORS ongoing health
              |
              +---> (anomaly) DeepField escalates
              +---> StarGate re-evaluates against rubrics
              +---> Launchpad takes action (reset/reclaim)
```

### Graceful Degradation

Every integration fails open. Each product works fully standalone.

| Condition | Behavior |
|-----------|----------|
| `STARGATE_API_URL` not set | Launchpad skips StarGate push, pre-flight returns `allowed=true` |
| `DEEPFIELD_API_URL` not set | Launchpad and StarGate skip DeepField push |
| `LAUNCHPAD_API_URL` not set | StarGate and DeepField skip callback push |
| StarGate returns non-200 | Launchpad logs at debug, continues normally |
| Network error to any target | Caught, logged at debug, no impact on source |

### Shared Event Schema

All three products use the same envelope:

```json
{
  "source": "launchpad | stargate | deepfield",
  "event_type": "session.ready | evaluation_result | remediation_suggestion",
  "event_id": "uuid (for deduplication)",
  "timestamp": "2026-05-26T12:00:00Z",
  "payload": {
    "session_id": "...",
    "outcome": "pass | fail | info",
    "...": "source-specific fields"
  }
}
```

### Security

- **Authentication:** `INTEGRATION_API_KEY` env var on each product. When set, inbound requests must include matching `X-API-Key` header.
- **Deduplication:** LRU cache of 10K event_ids. Duplicate events are rejected.
- **TLS:** `INTEGRATION_SSL_VERIFY` defaults to `true`. Set to `false` only for self-signed certs in dev.
- **CORS:** Configurable via `CORS_ORIGINS` env var. Explicit allowed methods and headers.

---

## Tech Stack (Aligned Across All Three)

| Component | Version |
|-----------|---------|
| Python | >=3.11 |
| FastAPI | >=0.115 |
| Pydantic | >=2.10 |
| asyncpg | >=0.30 |
| httpx | >=0.28 |
| API prefix | `/api/v1/` (product routes), `/integration/` (cross-product) |
| Base image | UBI9/python-311 |
| Container tool | Podman |
| Deployment | Kustomize + AgnosticV/AgnosticD |
| Frontend | React 19, TypeScript 6, Vite 8 |
| Frontend styling | Tailwind (portal/admin/DeepField) + PatternFly (demos) |

---

## Deployment

### Current State

| Product | GitHub | infra01 | RHDP Catalog |
|---------|--------|---------|-------------|
| Launchpad | https://github.com/rhpds/launchpad | Running | PR submitted (`launchpad-demos` branch in `rhpds/agnosticv`) |
| Partnership Demo | https://github.com/rhpds/red-hat-intel-partnership-demo | — | Standalone |
| StarGate | Local | Parked | Not registered |
| DeepField | https://github.com/rhpds/deepfield | Parked | Not registered |

### RHDP Deployment Pattern

Launchpad follows the standard RHDP pattern:

```
demo.redhat.com (user orders)
        |
        v
Babylon (orchestration)
        |
        v
AgnosticV catalog entry (common.yaml + env overrides)
        |
        v
AgnosticD playbook (workloads: keycloak, namespace, LiteLLM keys, GitOps, Showroom)
        |
        v
ArgoCD deploys tenant/bootstrap/ Helm chart
        |
        v
Per-user namespace with demo frontend + gateway + postgres
```

### CI/CD

All repos have GitHub Actions:

| Trigger | What Runs |
|---------|-----------|
| Push to main / PR | Tests + lint + image build (no push) + test receipt |
| Manual deploy workflow | Confirmation gate → full test suite → environment approval → deploy |

---

## Partnership Demo → Launchpad Code Flow

The partnership demo is the sandbox where inference gateway features are proven. Code graduates to Launchpad via copy-paste.

```
Partnership Demo (sandbox)          Launchpad (production)
========================          ========================

gateway/                   -->    demos/gateway/
  router.py                         router.py
  overdrive/                        overdrive/
  db.py                             db.py
  auth.py                           auth.py

frontend/src/pages/        -->    demos/frontend/src/pages/
  OverdrivePage.tsx                  OverdrivePage.tsx
  ResearchAgentPage.tsx              ResearchAgentPage.tsx
  ...                                ...

containers/vllm-cpu/       -->    demos/containers/vllm-cpu/
containers/vllm-gaudi/     -->    demos/containers/vllm-gaudi/
```

The two codebases are currently 99% identical in the gateway and frontend. This is intentional — the sandbox runs ahead, Launchpad follows.

---

## Environment Variables Reference

### Launchpad

| Variable | Required | Description |
|----------|----------|-------------|
| `LAUNCHPAD_MODE` | No | `mock` (default), `local`, `openshift`, `rhdp` |
| `DATABASE_URL` | No | PostgreSQL connection. Falls back to in-memory. |
| `STARGATE_API_URL` | No | StarGate base URL for event push + pre-flight. |
| `STARGATE_API_KEY` | No | API key for StarGate authentication. |
| `DEEPFIELD_API_URL` | No | DeepField base URL for event push. |
| `DEEPFIELD_API_KEY` | No | API key for DeepField authentication. |
| `INTEGRATION_API_KEY` | No | Required on inbound callbacks when set. |
| `CORS_ORIGINS` | No | Comma-separated allowed origins. |
| `AUTH_ENABLED` | No | `true` to enable OAuth/API key auth. |
| `API_KEYS` | No | Comma-separated valid API keys. |
| `ADMIN_API_KEYS` | No | Comma-separated admin API keys. |

### StarGate

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | No | PostgreSQL connection. Falls back to in-memory. |
| `DEEPFIELD_API_URL` | No | DeepField base URL for evaluation result push. |
| `DEEPFIELD_API_KEY` | No | API key for DeepField authentication. |
| `LAUNCHPAD_API_URL` | No | Launchpad base URL for cleanup result push. |
| `LAUNCHPAD_API_KEY` | No | API key for Launchpad authentication. |
| `INTEGRATION_API_KEY` | No | Required on inbound events when set. |
| `INTEGRATION_SSL_VERIFY` | No | `false` to skip TLS verification. Default: `true`. |
| `CORS_ORIGINS` | No | Comma-separated allowed origins. |

### DeepField

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | No | PostgreSQL connection. Runs without DB if not set. |
| `LITELLM_API_BASE` | No | LiteLLM proxy URL for inference. |
| `LITELLM_API_KEY` | No | API key for LiteLLM. |
| `LAUNCHPAD_API_URL` | No | Launchpad base URL for remediation push. |
| `LAUNCHPAD_API_KEY` | No | API key for Launchpad authentication. |
| `INTEGRATION_API_KEY` | No | Required on inbound events when set. |
| `INTEGRATION_SSL_VERIFY` | No | `false` to skip TLS verification. Default: `true`. |
| `CORS_ORIGINS` | No | Comma-separated allowed origins. |
| `CLUSTER_1_NAME` | No | Display name of monitored cluster. |
| `CLUSTER_1_API_URL` | No | K8s API URL of monitored cluster. |
| `CLUSTER_1_TOKEN` | No | ServiceAccount token (cluster-reader role). |
| `THANOS_URL` | No | Thanos/Prometheus endpoint for GPU metrics. |
