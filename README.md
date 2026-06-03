# Intel x Red Hat AI Partner Launchpad

![CI](https://github.com/rhpds/launchpad/actions/workflows/ci.yml/badge.svg)

Intelligent provisioning platform for AI lab environments on Red Hat OpenShift, powered by Intel Gaudi 3 accelerators and Xeon 6 processors. Launchpad is the orchestration brain for the Intel x Red Hat AI ecosystem — it classifies workloads, selects optimal hardware and clusters, learns from provisioning outcomes, and coordinates real-time signals from StarGate (validation) and DeepField (fleet observability) into unified placement decisions.

## What It Does

One-click access to pre-built AI demos running on real hardware, with intelligent placement. Each demo provisions an isolated environment with its own namespace, inference gateway, model routing, and LiteLLM virtual API key. The intelligence layer automatically classifies the workload, matches it to the best hardware profile, selects the healthiest cluster, and records the outcome to improve future decisions.

**10 custom demos** built by the Intel x Red Hat partnership:

| Demo | What It Shows |
|------|--------------|
| **Inference Overdrive** | Real-time model routing across 5 models — compare Gaudi vs Xeon latency and throughput |
| **Enterprise RAG** | Retrieval-augmented generation with vector search, embedding on Xeon, generation on Gaudi |
| **Agent Swarm** | Multi-agent parallel execution — multiple models coordinate on complex tasks |
| **Research Agent** | Multi-step document analysis with query decomposition, reranking, and citations |
| **AIOps Copilot** | Alert classification, root cause analysis, and governance-gated remediation |
| **Governed Agent** | Risk-gated AI agent execution with policy enforcement and audit logging |
| **Hardware Recovery** | Graceful failover from Gaudi to CPU — transparent to the caller |
| **Workload Generator** | Load testing with storm, barrage, and token-cannon modes |
| **Model Training** | Fine-tuning workflows on Intel Gaudi with evaluation |
| **Replay Comparison** | Side-by-side Xeon vs Gaudi performance benchmarking |

**7 official Red Hat AI Quickstarts** from Summit, deployed via existing RHDP catalog items:

- Enterprise RAG Chatbot
- Data Governance
- PPE Compliance Monitor
- Product Recommendation
- IT Self-Service
- LLM CPU Serving (Intel Xeon)
- vLLM Tool Calling (Granite 3.2)

## Architecture

```
LabRequest
    │
    ▼
OrchestrationBrain.decide()
    ├── WorkloadClassifier  → workload type, GPU required, intensity
    ├── PlacementService    → best cluster (StarGate capacity + feedback history)
    ├── DeepFieldAdapter    → fleet health signals
    └── FeedbackTracker     → historical success rates, avoid-list
    │
    ▼
ProvisioningService.provision()
    ├── pool.reserve(preferred_cluster=recommendation)
    ├── Sandbox API → namespace on CNV cluster
    ├── ArgoCD → tenant Helm chart
    └── After validation → FeedbackTracker.record_outcome()
    │
    ▼
  ┌────────────────────────────────────────────────────────┐
  │  Per-Tenant Namespace                                  │
  │  ┌──────────────┐  ┌────────────┐  ┌──────────────┐   │
  │  │ Demo Frontend │  │  Gateway   │  │  PostgreSQL  │   │
  │  │ (filtered     │─▶│ (routing   │  │  (state)     │   │
  │  │  pages)       │  │  policy)   │  └──────────────┘   │
  │  └──────────────┘  └─────┬──────┘                      │
  └──────────────────────────┼─────────────────────────────┘
                             │
                             ▼
                    LiteMaaS (LiteLLM)
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Intel Gaudi 3  Intel Xeon 6   llama.cpp
```

### Key Components

| Component | Purpose |
|-----------|---------|
| **OrchestrationBrain** | Composes all intelligence signals into unified placement decisions |
| **WorkloadClassifier** | Classifies workloads (CPU/GPU/training/RAG/agent/mixed) and matches to hardware |
| **PlacementService** | Recommends clusters based on StarGate capacity scores with caching |
| **FeedbackTracker** | Tracks provisioning outcomes, computes success rates, maintains avoid-list |
| **DeepFieldAdapter** | Integrates fleet health signals (CPU, GPU utilization, error rates) |
| **Sandbox API** | RHDP cluster pool manager — assigns namespaces on shared OpenShift clusters |
| **Inference Gateway** | FastAPI service implementing model routing policy across Intel hardware |
| **LiteMaaS** | LiteLLM proxy providing unified OpenAI-compatible API across all models |
| **Showroom** | Interactive lab UI with step-by-step instructions, terminal, and console tabs |

### Intelligence Layer

The intelligence layer makes provisioning decisions smarter over time:

1. **Workload Profiling** — classifies each catalog item by compute type, GPU requirements, and I/O pattern
2. **Smart Placement** — selects clusters based on capacity scores from StarGate, penalized by DeepField critical signals
3. **Feedback Loops** — records success/failure per catalog×cluster×hardware tuple; avoids combinations with <30% success rate
4. **Orchestration Brain** — coordinates all signals into a single decision with confidence scoring and rationale
5. **Graceful Degradation** — each signal source fails open; if all external systems are down, Launchpad provisions exactly as a static system would

## How It Works

### For Users

1. Order a demo from the RHDP catalog at demo.redhat.com
2. Receive a Showroom URL with SSO credentials
3. Follow the step-by-step lab instructions in the left panel
4. Interact with the demo in the right panel (terminal, console, or demo portal)
5. Environment automatically reclaims after the configured TTL

### For Operators

1. The **cluster config** (`launchpad-cluster`) provisions shared base infrastructure once — RHOAI, GitOps, Keycloak on a CNV pool cluster
2. Each **tenant config** (`launchpad-*-tenant`) creates an isolated per-user environment on the shared cluster
3. The Sandbox API manages capacity, quotas, and lifecycle
4. Each tenant gets its own LiteLLM virtual key for usage tracking and rate limiting

## Tech Stack

- **Backend:** Python >=3.11, FastAPI >=0.115, Pydantic >=2.10, asyncpg >=0.30
- **Database:** PostgreSQL via asyncpg (with in-memory fallback for testing)
- **Background tasks:** Celery + Redis (6 beat tasks: TTL enforcement, session cleanup, capacity sync, feedback sync, health check, rebalance)
- **Frontends:** React 19, Vite 8, TypeScript 6 — Tailwind (portal/admin) + PatternFly (demos)
- **API prefix:** All routes under `/api/v1/`
- **Deployment:** Kustomize manifests, UBI9 containers, internal OpenShift registry
- **Complementary systems:** StarGate (rubric validation), DeepField (fleet observability)

## Repository Structure

```
launchpad/
├── backend/
│   └── app/
│       ├── adapters/           # Mock, local, OpenShift, RHDP, DeepField adapter tiers
│       ├── domain/             # Pydantic models: lifecycle, placement, workload, feedback, orchestration
│       ├── services/           # Provisioning, placement, workload classifier, feedback tracker, orchestration brain
│       ├── api/routers/        # REST endpoints including intelligence API
│       ├── integrations/       # Event publisher (StarGate, Kafka, Dashboard)
│       └── prompts/            # YAML prompt templates (branding, workload classification, placement decision)
│   ├── tasks/                  # Celery tasks: lifecycle, capacity sync, feedback sync, orchestration
│   └── migrations/             # PostgreSQL schema (001 initial, 002 provisioning outcomes)
├── frontend/                   # Partner portal — DecisionInsight on SessionDetail
├── admin/                      # Admin dashboard — ProvisioningAnalytics page, DecisionInsight
├── demos/
│   ├── frontend/               # Demo frontend — FleetIntelligence dashboard, 18+ pages
│   └── gateway/                # Inference gateway (FastAPI, routing policy)
├── content/                    # Showroom lab content (Antora/AsciiDoc)
├── tenant/bootstrap/           # Helm chart deployed per-user by ArgoCD
├── deploy/
│   ├── agnosticv/              # RHDP catalog item configs (12 items)
│   └── launchpad/              # Kustomize manifests (infra01 overlay)
└── docs/                       # Architecture and process documentation
```

## Models

All models served via KServe on OpenShift AI, accessed through LiteMaaS:

| Model | Hardware | Use Case |
|-------|----------|----------|
| Granite 3.2 8B Instruct | Intel Gaudi 3 | General-purpose generation, classification |
| Llama 3.1 70B | CPU (llama.cpp) | Large-scale reasoning |
| DeepSeek R1 Distill Qwen 14B | Intel Gaudi 3 | Deep reasoning, chain-of-thought |
| Microsoft Phi-4 | Intel Gaudi 3 | Efficient small-model inference |
| Qwen3 14B | Intel Gaudi 3 | Multilingual generation, tool calling |

## Infrastructure

- **Compute:** Intel Gaudi 3 (24 cards across 3 nodes) + Intel Xeon 6
- **Platform:** Red Hat OpenShift 4.18+ with OpenShift AI 2.25
- **Cluster pools:** Managed by RHDP Sandbox API across CNV clusters
- **Deployment:** AgnosticD + ArgoCD (GitOps)
- **Auth:** Keycloak SSO + LiteLLM virtual keys per tenant

## Deployed

Live on infra01:

| App | URL |
|-----|-----|
| Partner Portal | https://launchpad.apps.ocpv-infra01.dal12.infra.demo.redhat.com |
| Admin Dashboard | https://launchpad-admin.apps.ocpv-infra01.dal12.infra.demo.redhat.com |
| Backend API | https://launchpad-api.apps.ocpv-infra01.dal12.infra.demo.redhat.com |

## Roadmap

### Done

- [x] Backend — FastAPI with domain models, lifecycle state machine, adapter pattern (mock/local/openshift/rhdp)
- [x] Intelligence layer — PlacementService, WorkloadClassifier, FeedbackTracker, OrchestrationBrain, DeepFieldAdapter
- [x] Intelligence API — 7 endpoints (fleet-health, decision audit, simulate, cluster signals, feedback summary)
- [x] Partner portal — React frontend with branding, demo catalog, sandbox configuration, DecisionInsight
- [x] Admin dashboard — session management, tenant management, ProvisioningAnalytics page, DecisionInsight
- [x] Demo frontend — 18+ pages including FleetIntelligence dashboard, CockpitDashboard, Operations
- [x] Inference gateway — FastAPI routing policy across Gaudi/Xeon/CPU backends
- [x] RHDP integration — Sandbox API client, AgnosticV configs (12), ArgoCD tenant Helm chart, Showroom content
- [x] Catalog — 25 items (10 custom demos, 7 official quickstarts, 4 sandboxes, 4 originals)
- [x] Celery beat — 6 scheduled tasks (TTL, cleanup, capacity sync, feedback sync, health check, rebalance)
- [x] Database — PostgreSQL with migrations (001 initial schema, 002 provisioning outcomes)
- [x] Security — SSO, API keys, session limits, PSS, NetworkPolicy, credential scrubbing
- [x] 507 backend tests — all TDD red/green
- [x] Deployed to infra01 — backend, portal, admin all running

### Configuration

| Flag | Default | Purpose |
|------|---------|---------|
| `SMART_PLACEMENT_ENABLED` | `true` | Cluster selection via StarGate capacity scores |
| `WORKLOAD_PROFILING_ENABLED` | `false` | Workload classification and hardware matching |
| `FEEDBACK_TRACKING_ENABLED` | `false` | Provisioning outcome tracking and avoid-list |
| `ORCHESTRATION_BRAIN_ENABLED` | `false` | Unified decision engine composing all signals |
| `DEEPFIELD_API_URL` | (empty) | DeepField fleet observability endpoint |
| `STARGATE_API_URL` | (empty) | StarGate validation and capacity endpoint |

## Development

```bash
# Run locally with mock adapters
cd backend
LAUNCHPAD_MODE=mock uvicorn app.main:app --reload

# Run tests
python -m pytest tests/ -q

# Run with RHDP integration (requires VPN + Sandbox API token)
LAUNCHPAD_MODE=rhdp \
SANDBOX_API_URL=$SANDBOX_API_URL \
SANDBOX_LOGIN_TOKEN=$(cat ~/.sandbox/token) \
HTTPS_PROXY=$HTTPS_PROXY \
uvicorn app.main:app --reload
```
