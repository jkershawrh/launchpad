# Intel x Red Hat AI Partner Launchpad

![CI](https://github.com/rhpds/launchpad/actions/workflows/ci.yml/badge.svg)

Self-service demo platform that provisions AI lab environments on Red Hat OpenShift, powered by Intel Gaudi 3 accelerators and Xeon 6 processors. Integrates with the Red Hat Demo Platform (RHDP) to deliver repeatable, branded, time-boxed AI experiences for partners, customers, and internal teams.

## What It Does

One-click access to pre-built AI demos running on real hardware. Each demo provisions an isolated environment with its own namespace, inference gateway, model routing, and LiteLLM virtual API key — backed by Intel Gaudi 3 for accelerated inference and Intel Xeon 6 for CPU-optimized workloads.

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
User orders demo from RHDP catalog
        │
        ▼
  Babylon (orchestration)
        │
        ▼
  Sandbox API ──► Assigns namespace on shared CNV cluster
        │
        ▼
  AgnosticD ──► Runs workloads (Keycloak, namespace, LiteLLM keys, GitOps)
        │
        ▼
  ArgoCD ──► Deploys tenant/bootstrap/ Helm chart
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
         (Granite, Phi, (embeddings,   (Llama 70B)
          DeepSeek,      classification)
          Qwen)
```

### Key Components

| Component | Purpose |
|-----------|---------|
| **Sandbox API** | RHDP cluster pool manager — assigns namespaces on shared OpenShift clusters |
| **AgnosticD** | Ansible-based deployment automation — installs operators and workloads |
| **ArgoCD** | GitOps delivery — deploys the tenant Helm chart per user |
| **Inference Gateway** | FastAPI service implementing model routing policy across Intel hardware |
| **LiteMaaS** | LiteLLM proxy providing unified OpenAI-compatible API across all models |
| **Showroom** | Interactive lab UI with step-by-step instructions, terminal, and console tabs |
| **Demo Frontend** | React application with runtime page filtering via ConfigMap |

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
- **Frontends:** React 19, Vite 8, TypeScript 6 — Tailwind (portal/admin) + PatternFly (demos)
- **API prefix:** All routes under `/api/v1/`
- **Deployment:** AgnosticD + ArgoCD, Kustomize manifests, UBI9 containers, Podman

## Repository Structure

```
launchpad/
├── backend/                    # FastAPI backend — lifecycle, provisioning, adapters
│   └── app/
│       ├── adapters/           # Mock, local, OpenShift, and RHDP adapter tiers
│       │   └── rhdp/           # Sandbox API client and RHDP provisioning
│       ├── domain/             # Pydantic models, enums, state machine
│       ├── services/           # Provisioning service, lifecycle management
│       └── api/                # REST API endpoints
├── frontend/                   # Partner portal (React/Vite/Tailwind)
├── admin/                      # Admin dashboard (React/Vite/Tailwind)
├── demos/
│   ├── frontend/               # Demo frontend (React, runtime page filtering)
│   └── gateway/                # Inference gateway (FastAPI, routing policy)
├── content/                    # Showroom lab content (Antora/AsciiDoc)
│   └── modules/ROOT/pages/     # 12 lab guide pages
├── tenant/
│   └── bootstrap/              # Helm chart deployed per-user by ArgoCD
├── deploy/
│   ├── agnosticv/              # RHDP catalog item configs (cluster + tenant)
│   └── launchpad/              # Kustomize manifests for Launchpad platform
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

## Roadmap

### Done

- [x] Backend — FastAPI with domain models, lifecycle state machine, adapter pattern (mock/local/openshift/rhdp)
- [x] Partner portal — React frontend with branding, demo catalog, sandbox configuration
- [x] Admin dashboard — session management, tenant management, catalog CRUD, system status
- [x] Demo frontend — runtime page filtering via ConfigMap, 10 demo pages
- [x] Inference gateway — FastAPI routing policy across Gaudi/Xeon/CPU backends
- [x] RHDP integration — Sandbox API client, AgnosticV configs (12), ArgoCD tenant Helm chart, Showroom content (12 pages)
- [x] Catalog — 25 items (10 custom demos, 7 official quickstarts, 4 sandboxes, 4 originals)
- [x] Workshop batch provisioning — bulk provision/reclaim N sessions
- [x] Persistent demos — never expires, reinitialize without destroying
- [x] Security — SSO, API keys, session limits, PSS, NetworkPolicy, credential scrubbing, kubeconfig
- [x] Cleanup — TTL enforcement, gateway lock, timeout fatal, orphaned RoleBinding cleanup, audit trail
- [x] 422 unit tests — all TDD red/green
- [x] GitHub Actions CI — tests, lint, TypeScript, Helm, image builds on every push

### Waiting On (external)

- [ ] Sandbox API `app` role token — need admin to issue
- [ ] quay.io push access — need to be added to `rhpds` org
- [ ] AgnosticV PR review — branch `launchpad-demos` in `rhpds/agnosticv`

### To Do (once unblocked)

- [ ] Push container images to quay.io
- [ ] End-to-end test on dev CNV cluster via Sandbox API
- [ ] Full RHDP pipeline test — Babylon → AgnosticD → ArgoCD → Showroom
- [ ] Showroom screenshots from running demo
- [ ] Move from dev → integration → prod

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
